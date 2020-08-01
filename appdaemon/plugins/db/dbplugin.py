import asyncio
import copy
import os
import json
from pymysql import err as SQLERR
import datetime
import iso8601

from databases import Database
from appdaemon.appdaemon import AppDaemon
from appdaemon.plugin_management import PluginBase
import appdaemon.utils as utils

import traceback


class DbPlugin(PluginBase):
    def __init__(self, ad: AppDaemon, name, args):
        super().__init__(ad, name, args)

        self.AD = ad
        self.stopping = False
        self.config = args
        self.name = name
        self.initialized = False
        self.state = {}
        self._lock = None
        self._namespaces = {}

        if "namespace" in self.config:
            self.namespace = self.config["namespace"]
        else:
            self.namespace = "default"

        self.logger.info("Database Plugin Initializing")

        self.connection_url = self.config.get("connection_url")

        if isinstance(self.connection_url, str) and "ssl" not in self.connection_url:
            self.ssl = False

        else:
            self.ssl = None

        databases = self.config.get("databases", {})

        if isinstance(databases, str):
            databases = databases.split(",")

        self.databases = {}
        if isinstance(databases, list):
            for db in databases:
                self.databases[db] = None

        else:
            self.databases = databases

        self.database_connections = {}
        self.connection_pool = int(self.config.get("connection_pool", 20))

        if self.connection_pool < 5:
            self.logger.warning(
                "Cannot use %s for Connection Pool, must be higher than 5. Reverting to 6", self.connection_pool
            )
            self.connection_pool = 6

        if self.connection_url is None:  # by default make use of the sqlite
            connection_url = os.path.join(self.AD.config_dir, "databases")
            if not os.path.isdir(connection_url):  # it doesn't exist
                try:
                    os.makedirs(connection_url)

                except Exception:
                    raise Exception(
                        "Cannot create directory %s for database", connection_url,
                    )

            self.connection_url = f"sqlite:///{connection_url}"

        self.loop = self.AD.loop  # get AD loop

        self.database_metadata = {
            "version": "1.0",
            "connection_url": self.connection_url,
            "databases": list(self.databases.keys()),
            "connection_pool": self.connection_pool,
        }

    def stop(self):
        self.logger.debug("stop() called for %s", self.name)

        self.stopping = True
        # set to continue
        self._event.set()

        self.logger.info("Stopping Database Plugin")

        if len(self.database_connections) > 0:
            for database, connection in self.database_connections.items():
                self.logger.info(
                    "Closing Database Connection to %s", f"{self.connection_url}/{database}",
                )
                self.loop.create_task(connection.disconnect())

    #
    # Placeholder for constraints
    #
    def list_constraints(self):
        return []

    #
    # Get initial state
    #

    async def get_complete_state(self):
        self.logger.debug("*** Sending Complete State: %s ***", self.state)
        return copy.deepcopy(self.state)

    async def get_metadata(self):
        return self.database_metadata

    #
    # Utility gets called every second (or longer if configured
    # Allows plugin to do any housekeeping required
    #

    def utility(self):
        # self.logger.info("*** Utility ***".format(self.state))
        return

    #
    # Handle state updates
    #

    async def get_updates(self):
        already_notified = False
        first_time = True
        self.reading = False
        self._event = asyncio.Event()

        # set to continue
        self._event.set()

        while not self.stopping:
            await self._event.wait()

            while len(self.databases) != len(self.database_connections):
                # now create the connection to the databases
                # and store the connections
                for database in self.databases:
                    if database in self.database_connections:
                        continue

                    entity_id = f"database.{database.lower()}"
                    kwargs = {}
                    kwargs["attributes"] = {}

                    try:
                        if entity_id not in self.state:
                            kwargs["attributes"]["friendly_name"] = f"{database.title()} Database"
                            kwargs["attributes"]["url"] = None

                        if self.connection_url.startswith("sqlite:///"):

                            if self._lock is None:
                                self._lock = {}

                            database_url = os.path.join(self.connection_url, f"{database}.db")
                            self.logger.debug(
                                "Creating connection to Database %s", database_url,
                            )

                            self.database_connections[database] = Database(database_url)

                            self._lock[database] = asyncio.Lock()  # lock will be used to access the connection

                            increment = "AUTOINCREMENT"  # to be used later

                        else:
                            # first will need confirmation
                            # that the database exists,
                            # so attempt creating it
                            query = f"""CREATE DATABASE IF NOT EXISTS
                                    {database}"""

                            await self.database_create(database, query)

                            increment = "AUTO_INCREMENT"  # to be used later

                            database_url = f"{self.connection_url}/{database}"
                            self.logger.debug(
                                "Creating connection to Database %s", database_url,
                            )

                            prams = {}
                            if self.ssl is not None:
                                prams["ssl"] = self.ssl

                            prams["min_size"] = 5
                            prams["max_size"] = self.connection_pool

                            self.database_connections[database] = Database(database_url, **prams)

                        await self.database_connections[database].connect()

                        self.logger.info("Connected to Database using URL %s", database_url)

                        kwargs["state"] = "connected"
                        kwargs["attributes"]["url"] = database_url

                    except Exception as e:
                        if database in self.database_connections:
                            del self.database_connections[database]

                            if self._lock is not None and database in self._lock:
                                del self._lock[database]

                        self.logger.error("-" * 60)
                        self.logger.error(
                            "Could not setup connection to database %s", database_url,
                        )
                        self.logger.error("-" * 60)
                        self.logger.error(e)
                        self.logger.debug(traceback.format_exc())
                        self.logger.error("-" * 60)

                        kwargs["state"] = "disconnected"

                    await self.state_update(entity_id, kwargs, not first_time)

                if len(self.database_connections) > 0:  # at least 1 of them connected
                    executed = await self.process_databases(increment)

                    if executed is False:
                        break

                    states = await self.get_complete_state()

                    await self.AD.plugins.notify_plugin_started(
                        self.name, self.namespace, self.database_metadata, states, first_time,
                    )

                    asyncio.ensure_future(self.check_database_sizes())

                    first_time = False
                    already_notified = False

                elif len(self.database_connections) == 0 and already_notified is False:
                    await self.AD.plugins.notify_plugin_stopped(self.name, self.namespace)
                    already_notified = True

                if len(self.databases) != len(self.database_connections):  # some did not work
                    self.logger.warning("Could not connect to all Databases, will attempt in 5 seconds")

                elif len(self.databases) == len(self.database_connections):  # all initialized, so can wait
                    self._event.clear()  # it should stop

            await asyncio.sleep(5)

    async def process_databases(self, increment):
        """Process the databases"""
        execs = []

        for database in self.database_connections:
            if self.databases[database] is None:
                continue

            if await self.check_database(database):  # it is to be used by AD
                # there are one of the those settings, so most likely a namespace
                # need to setup entities and events database

                # first get the namespace
                # if no namespace specified, it should use the name by default

                _namespace = self.databases.get("namespace", database)

                if _namespace not in self._namespaces:
                    self._namespaces[_namespace] = {}
                    self._namespaces[_namespace]["handle"] = None
                    self._namespaces[_namespace]["databases"] = []

                if database not in self._namespaces[_namespace]["databases"]:
                    self._namespaces[_namespace]["databases"].append(database)

                # next we need to ensure we create the states tables
                query = f"""CREATE TABLE IF NOT EXISTS states (
                        state_id INTEGER NOT NULL PRIMARY KEY {increment},
                        domain VARCHAR(100),
                        entity_id VARCHAR(100),
                        state VARCHAR(512),
                        attributes TEXT,
                        last_changed DATETIME,
                        timestamp DATETIME)"""

                executed = await self.database_execute(database, query, None)

                execs.append(executed)

                # next we need to ensure we create the events tables
                query = f"""CREATE TABLE IF NOT EXISTS events (
                        event_id INTEGER NOT NULL PRIMARY KEY {increment},
                        event_type VARCHAR(100),
                        event_data TEXT,
                        timestamp DATETIME)"""

                executed = await self.database_execute(database, query, None)

                execs.append(executed)

                if executed is True:
                    handle = self._namespaces[_namespace]["handle"]
                    if handle is not None:
                        continue  # already been setup do no need

                    self._namespaces[_namespace]["handle"] = await self.AD.events.add_event_callback(
                        self.name, _namespace, self.event_callback, None, __silent=True, __namespace=_namespace,
                    )

                else:  # it didn't create the table as requested
                    await self.database_connections[database].disconnect()
                    del self.database_connections[database]
                    break

        if (
            all(execs) is False
        ):  # there  was an error when processing one of the tables, so no need continuing processing
            return False

        self.AD.services.register_service(
            self.namespace, "database", "execute", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "database", "fetch_one", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "database", "fetch_all", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "database", "create", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "database", "drop", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "database", "get_history", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "server", "execute", self.call_plugin_service,
        )
        self.AD.services.register_service(
            self.namespace, "server", "fetch", self.call_plugin_service,
        )

        return True

    #
    # Service Call
    #

    async def call_plugin_service(self, namespace, domain, service, kwargs):
        self.logger.debug(
            "call_plugin_service() namespace=%s domain=%s service=%s kwargs=%s", namespace, domain, service, kwargs,
        )
        res = None

        database = kwargs.get("database")
        query = kwargs.get("query")

        if database is None and domain != "server":
            self.logger.warning("Could not execute service call, as Database not provided")
            return res

        elif query is None and service not in ["drop", "create"]:
            self.logger.warning("Could not execute service call, as Query not provided")
            return res

        kwargs["service"] = service

        if domain == "database":
            res = await self.database_service(**kwargs)

        elif domain == "server":
            res = await self.server_service(**kwargs)

        return res

    async def database_service(self, **kwargs):
        """Database Service"""

        res = None
        database = kwargs.get("database")
        values = kwargs.get("values")
        query = kwargs.get("query")
        service = kwargs["service"]

        if service == "execute":
            asyncio.ensure_future(self.database_execute(database, query, values))

        elif service == "fetch_one":
            res = await self.database_fetch(database, query, values, "one")

        elif service == "fetch_all":
            res = await self.database_fetch(database, query, values, "all")

        elif service == "create":
            if database in self.databases:
                self.logger.warning(
                    "Cannot create Database %s, as it already exists", database,
                )
                return

            executed = await self.database_create(database, query)
            if executed is True:
                self._event.set()  # continue to process connection

        elif service == "drop":
            if database not in self.databases:
                self.logger.warning(
                    "Cannot drop Database %s, as it doesn't exists", database,
                )
                return None

            if await self.check_database(database):
                self.logger.warning("Cannot drop Database %s, as it used by AD", database)
                return None

            await self.database_drop(database, kwargs.get("clean", False))

        elif service == "get_history":
            return await self.get_history(**kwargs)

        return res

    async def server_service(self, **kwargs):
        """Server Service"""

        res = None
        values = kwargs.get("values")
        query = kwargs.get("query")
        service = kwargs["service"]

        if service == "execute":
            asyncio.ensure_future(self.server_execute(query, values))

        elif service == "fetch":
            if not self.connection_url.startswith("sqlite:///"):
                try:
                    async with Database(self.connection_url) as connection:
                        res = await connection.fetch_all(query=query)

                except Exception as e:
                    self.logger.error("-" * 60)
                    self.logger.error("-" * 60)
                    self.logger.error(e)
                    self.logger.debug(traceback.format_exc())
                    self.logger.error("-" * 60)

        return res

    async def database_create(self, database, query=None):
        """Used to create a database"""

        executed = True
        if not self.connection_url.startswith("sqlite:///"):
            if query is None:
                query = f"CREATE DATABASE {database}"

            try:
                async with Database(self.connection_url) as connection:
                    await connection.execute(query=query)

            except SQLERR.ProgrammingError as p:
                if p.args[0] == 1007:  # it already exists
                    self.logger.info(
                        "Database %s already existing, so couldn't create it", database,
                    )

            except Exception as e:
                executed = False
                self.logger.error("-" * 60)
                self.logger.error("Could not create Database for %s", database)
                self.logger.error("-" * 60)
                self.logger.error(e)
                self.logger.debug(traceback.format_exc())
                self.logger.error("-" * 60)

        if executed is True:
            # now add it to the list, so the database is created
            if database not in self.databases:
                self.databases[database] = None

            if database not in self.database_metadata["databases"]:
                self.database_metadata["databases"].append(database)

        return executed

    async def database_drop(self, database, clean=False):
        """Used to drop a database"""

        try:
            await self.database_connections[database].disconnect()

            if not self.connection_url.startswith("sqlite:///"):
                async with Database(self.connection_url) as connection:
                    await connection.execute(query=f"DROP DATABASE {database}")

            else:
                # its sqlite so just delete it
                database_path = self.connection_url.replace("sqlite:///", "")
                database_url = os.path.join(database_path, f"{database}.db")

                if clean and await utils.run_in_executor(self, os.path.isfile, database_url):
                    await utils.run_in_executor(self, os.remove, database_url)

                if database in self._lock:
                    del self._lock[database]

            del self.database_connections[database]
            del self.databases[database]

            if database in self.database_metadata["databases"]:
                self.database_metadata["databases"].remove(database)

            ns = None

            # remove database from namespace
            for namespace in self._namespaces:
                if database in self._namespaces[namespace]["databases"]:
                    ns = namespace

                if ns is not None:
                    break

            if ns is not None:
                self._namespaces[ns]["databases"].remove(database)

            entity_id = f"database.{database.title()}"
            await self.AD.state.remove_entity(self.namespace, entity_id)
            if entity_id in self.state:
                del self.state[entity_id]

            self.logger.info("Removal of the Database %s was successful", database)

        except Exception as e:
            self.logger.error("-" * 60)
            self.logger.error("-" * 60)
            self.logger.error(e)
            self.logger.debug(traceback.format_exc())
            self.logger.error("-" * 60)

    async def database_execute(self, database, query, values):
        """Used to execute a database query"""

        executed = False

        if self._lock is not None:  # means sqlite used
            await self._lock[database].acquire()

        try:
            if database not in self.database_connections:
                self.logger.warning(
                    "Could not connect to Database %s, as no valid connection to it", database,
                )
                return executed

            connection = self.database_connections[database]

            if isinstance(values, list):
                await connection.execute_many(query=query, values=values)

            elif isinstance(values, dict) or values is None:
                await connection.execute(query=query, values=values)

            else:
                self.logger.warning(
                    "Invalid Values data provided. Cannot execute command. Must be either List or Dict Values: %s",
                    values,
                )

            executed = True

        except SQLERR.InternalError as i:
            self.logger.critical(i)

            if i.args[0] == 1049:  # its an internal error. Possible connection lost so will need to be restarted
                del self.database_connections[database]
                self._event.set()  # continue to process connection
                entity_id = f"database.{database.lower()}"
                await self.state_update(entity_id, {"state": "disconnected"})

        except Exception as e:
            self.logger.error("-" * 60)
            self.logger.error("Could not execute database query. %s %s", query, values)
            self.logger.error("-" * 60)
            self.logger.error(e)
            self.logger.debug(traceback.format_exc())
            self.logger.error("-" * 60)

        finally:
            if self._lock is not None:  # means sqlite used
                self._lock[database].release()

        return executed

    async def database_fetch(self, database, query, values, rows="all"):
        """Used to fetch data from a database"""

        res = None

        if self._lock is not None:  # means sqlite used
            await self._lock[database].acquire()

        try:
            if database not in self.database_connections:
                raise ValueError(
                    "Could not connect to Database %s, as no valid connection to it", database,
                )

            connection = self.database_connections[database]

            if rows == "all":
                res = await connection.fetch_all(query=query, values=values)

            else:
                res = await connection.fetch_one(query=query, values=values)

        except SQLERR.InternalError as i:
            self.logger.critical(i)

            if i.args[0] == 1049:  # its an internal error.
                # Possible connection lost so will need to be restarted
                del self.database_connections[database]
                self._event.set()  # continue to process connection
                entity_id = f"database.{database.lower()}"
                await self.state_update(entity_id, {"state": "disconnected"})

        except Exception as e:
            self.logger.error("-" * 60)
            self.logger.error("Could not execute database query. %s %s", query, values)
            self.logger.error("-" * 60)
            self.logger.error(e)
            self.logger.debug(traceback.format_exc())
            self.logger.error("-" * 60)

        finally:
            if self._lock is not None:  # means sqlite used
                self._lock[database].release()

        return res

    async def server_execute(self, query, values):
        if not self.connection_url.startswith("sqlite:///"):
            try:
                async with Database(self.connection_url) as connection:
                    await connection.execute(query=query, values=values)

            except Exception as e:
                self.logger.error("-" * 60)
                self.logger.error("-" * 60)
                self.logger.error(e)
                self.logger.debug(traceback.format_exc())
                self.logger.error("-" * 60)

    async def get_history(self, **kwargs):
        """Get the history of data from the database"""

        res = []
        entity_id = kwargs.get("entity_id")
        event = kwargs.get("event")
        databases = kwargs.get("database")
        table = kwargs.get("table")
        query = ""

        # first process time interval of the request
        start_time, end_time = self.get_history_time(**kwargs)

        if isinstance(databases, str):
            databases = databases.split(",")

        elif databases is None:
            databases = list(self.databases.keys())

        for database in databases:
            r = {}  # store data
            database = database.strip()

            if not await self.check_database(database):
                continue

            values = {}

            # decide if to get the
            if entity_id is not None:
                query = query + "SELECT * FROM states WHERE entity_id = :entity_id "
                values["entity_id"] = entity_id

            elif event is not None:
                query = query + "SELECT * FROM events WHERE event_type = :event "
                values["event"] = event

            elif table is not None and table in ["events", "states"]:
                query = f"SELECT * FROM {table} "
                values = None

            else:
                raise ValueError("Specify either entity_id, events, or table to access")

            st = start_time.strftime("%Y-%m-%d %H:%M:%S")
            et = end_time.strftime("%Y-%m-%d %H:%M:%S")

            if "WHERE" in query:
                query = query + "AND "

            else:
                query = query + "WHERE "

            query = (
                query
                + f"""timestamp BETWEEN '{st}'
                    AND '{et}' ORDER BY timestamp"""
            )
            r[database] = await self.database_fetch(database, query, values)

            res.append(r)

        return res

    def get_history_time(self, **kwargs):

        days = kwargs.get("days", 1)
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")

        if start_time is not None:
            if isinstance(start_time, str):
                start_time = utils.str_to_dt(start_time).replace(microsecond=0)
            elif isinstance(start_time, datetime.datetime):
                start_time = self.AD.tz.localize(start_time).replace(microsecond=0)
            else:
                raise ValueError("Invalid type for start time")

        if end_time is not None:
            if isinstance(end_time, str):
                end_time = utils.str_to_dt(end_time).replace(microsecond=0)
            elif isinstance(end_time, datetime.datetime):
                end_time = self.AD.tz.localize(end_time).replace(microsecond=0)
            else:
                raise ValueError("Invalid type for end time")

        if start_time is not None and end_time is None:
            end_time = start_time + datetime.timedelta(days=days)

        # if endtime is declared and start_time is not declared,
        # and days specified
        elif end_time is not None and start_time is None:
            start_time = end_time - datetime.timedelta(days=days)

        elif start_time is None and end_time is None:
            end_time = datetime.datetime.now()
            start_time = end_time - datetime.timedelta(days=days)

        return start_time, end_time

    async def event_callback(self, event, data, kwargs):
        self.logger.debug("event_callback: %s %s %s", kwargs, event, data)

        _namespace = kwargs["__namespace"]

        ts = await self.AD.sched.get_now()
        ts = ts.strftime("%Y-%m-%d %H:%M:%S")

        databases = self._namespaces[_namespace]["databases"]  # get the databases in this namespace

        for database in databases:
            if event == "state_changed":
                entity_id = data["entity_id"]

                if database not in self.databases or not await self.check_entity_id(database, entity_id):
                    continue

                new_state = data["new_state"]
                new_state.pop("entity_id", None)  # remove the entity_id if available, unnecessary data
                domain, _ = entity_id.split(".")

                states = await self.database_entity_id(database, entity_id, new_state)

                query = """INSERT INTO states
                        (domain, entity_id, state, attributes, last_changed, timestamp)
                        VALUES (:domain, :entity_id, :state, :attributes, :last_changed, :timestamp)"""

                state = states.get("state")
                if isinstance(state, dict):
                    state = json.dumps(state)

                attributes = states.get("attributes")
                if isinstance(attributes, dict):
                    attributes = json.dumps(attributes)

                lc = states.get("last_changed")
                if lc is None:
                    last_changed = ts

                else:
                    last_changed = iso8601.parse_date(lc).strftime("%Y-%m-%d %H:%M:%S")

                values = {
                    "domain": domain,
                    "entity_id": entity_id,
                    "state": state,
                    "attributes": attributes,
                    "last_changed": last_changed,
                    "timestamp": ts,
                }

            else:
                if not await self.check_event(database, event):  # should not be stored
                    continue

                query = """INSERT INTO events
                        (event_type, event_data, timestamp)
                        VALUES (:event_type, :event_data, :timestamp)"""

                values = {
                    "event_type": event,
                    "event_data": json.dumps(data),
                    "timestamp": ts,
                }

            if self.stopping is False:
                asyncio.ensure_future(self.database_execute(database, query, values))

    async def check_event(self, database, event):
        """Check if to store the event's data"""

        execute = False

        if "events" not in self.databases[database]:
            return execute

        events = self.databases[database]["events"]

        if events is None:
            execute = True

        else:
            if isinstance(events, str):
                if events == event or (events.endswith("*") and event.startswith(events[:-1])):
                    execute = True

            elif isinstance(events, list):
                for e in events:
                    if e == event:
                        execute = True

                    elif e.endswith("*") and event.startswith(e[:-1]):
                        execute = True

                    if execute is True:
                        break

        return execute

    async def check_entity_id(self, database, entity_id):
        """Check if to store the entity's data"""

        execute = True

        if self.databases[database] is None:
            # there is no filers used for the database
            pass

        elif "exclude_entities" in self.databases[database]:
            excluded_entities = self.databases[database]["exclude_entities"]

            if isinstance(excluded_entities, str):
                if excluded_entities == entity_id or (
                    excluded_entities.endswith("*") and entity_id.startswith(excluded_entities[:-1])
                ):
                    execute = False

            elif isinstance(excluded_entities, list):
                for entity in excluded_entities:
                    if entity == entity_id:
                        execute = False

                    elif entity.endswith("*") and entity_id.startswith(entity[:-1]):
                        execute = False

                    if execute is False:
                        break

        elif "inlude_entities" in self.databases[database]:
            execute = False
            included_entities = self.databases[database]["include_entities"]

            if isinstance(included_entities, str):
                if included_entities == entity_id or (
                    included_entities.endswith("*") and entity_id.startswith(included_entities[:-1])
                ):
                    execute = True

            elif isinstance(included_entities, list):
                for entity in included_entities:
                    if entity == entity_id:
                        execute = True

                    elif entity.endswith("*") and entity_id.startswith(entity[:-1]):
                        execute = True

                    if execute is True:
                        break

        return execute

    async def database_entity_id(self, database, entity_id, new_state):
        """Used to check if more filters applied"""

        remove_attributes = False
        state_only = False

        if self.databases[database] is None:
            return new_state

        if "exclude_attributes" in self.databases[database]:
            exclude_attributes = self.databases[database]["exclude_attributes"]
            if isinstance(exclude_attributes, list):
                for entity in exclude_attributes:
                    if entity == entity_id:
                        remove_attributes = True

                    elif entity.endswith("*") and entity_id.startswith(entity[:-1]):
                        remove_attributes = True

                    if remove_attributes is True:
                        break

                # now has finished, so check if to remove
                if remove_attributes is True:
                    new_state.pop("attributes", None)
                    return new_state

        if "states_only" in self.databases[database]:
            states_only = self.databases[database]["states_only"]
            if isinstance(states_only, list):
                for entity in states_only:
                    if entity == entity_id:
                        state_only = True

                    elif entity.endswith("*") and entity_id.startswith(entity[:-1]):
                        state_only = True

                    if state_only is True:
                        break

                # now has finished, so check if to send only state
                if state_only is True:
                    return {"state": new_state.get("state")}

        return new_state

    async def check_database(self, database):
        """Check if Database will be used by AD"""

        data = self.databases[database]
        options = [
            "include_entities",
            "exclude_entities",
            "states_only",
            "exclude_attributes",
            "events",
            "namespace",
        ]

        if isinstance(data, dict) and any(map(lambda x: x in data, options)):
            return True

        return False

    async def check_database_sizes(self):
        """Used to check database size every hour"""

        await asyncio.sleep(5)

        while not self.stopping:
            try:
                for database in self.database_connections:
                    entity_id = f"database.{database}"
                    kwargs = {}
                    kwargs["attributes"] = {}
                    size = 0

                    if self.connection_url.startswith("sqlite:///"):
                        # its sqlite so just delete it
                        database_path = self.connection_url.replace("sqlite:///", "")
                        database_url = os.path.join(database_path, f"{database}.db")

                        if os.path.isfile(database_url):
                            size = await utils.run_in_executor(self, os.path.getsize, database_url)

                    else:
                        pass
                        # async with Database(self.connection_url) as connection:
                        #    query = ""
                        #    await connection.execute(query=query)

                    kwargs["attributes"]["size_in_mega_bytes"] = size

                    self.logger.debug("Database size for %s retrieved as %s", database, size)

                    await self.state_update(entity_id, kwargs)

            except Exception as e:
                self.logger.error("-" * 60)
                self.logger.error("-" * 60)
                self.logger.error(e)
                self.logger.debug(traceback.format_exc())
                self.logger.error("-" * 60)

            await asyncio.sleep(3600)

    def get_namespace(self):
        return self.namespace

    async def state_update(self, entity_id, kwargs, notified=True):
        self.logger.debug("Updating State for Entity_ID %s, with %s", entity_id, kwargs)

        try:

            if entity_id in self.state:
                old_state = self.state[entity_id]

            else:
                # Its a new state entry
                self.state[entity_id] = {}
                old_state = {}
                old_state["attributes"] = {}

            new_state = copy.deepcopy(old_state)

            if "attributes" not in new_state:  # just to ensure
                new_state["attributes"] = {}

            if "state" in kwargs:
                new_state["state"] = kwargs["state"]
                del kwargs["state"]

            if "attributes" in kwargs:
                new_state["attributes"].update(kwargs["attributes"])

            else:
                new_state["attributes"].update(kwargs)

            if "_local" in new_state["attributes"]:  # check if there is local flag
                del new_state["attributes"]["_local"]  # delete it

            try:
                last_changed = utils.dt_to_str(
                    (await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz,
                )  # possible AD isn"t ready at this point
            except Exception:
                last_changed = None

            new_state["last_changed"] = last_changed

            if notified is True:  # AD had been updated of this namespace
                data = {
                    "event_type": "state_changed",
                    "data": {"entity_id": entity_id, "new_state": new_state, "old_state": old_state},
                }

                # this is put ahead, to ensure integrity of the data.
                # Breaks if not
                await self.AD.events.process_event(self.namespace, data)

            self.state[entity_id].update(new_state)

        except Exception as e:
            self.logger.error("-" * 60)
            self.logger.error("-" * 60)
            self.logger.error(e)
            self.logger.debug(traceback.format_exc())
            self.logger.error("-" * 60)
