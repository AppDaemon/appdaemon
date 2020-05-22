import asyncio
import copy
import os
import json
from pymysql import err as SQLERR
import datetime

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

        self.tables = self.config.get("tables", {})
        self.databases = self.config.get("databases", ["appdaemon"])

        if isinstance(self.databases, str):
            self.databases = self.databases.split(",")

        if self.tables != {} and "appdaemon" not in self.databases:
            self.databases.append("appdaemon")

        self.database_connections = {}
        self.connection_pool = int(self.config.get("connection_pool", 20))

        if self.connection_url is None:  # by default make use of the sqlite
            connection_url = os.path.join(self.AD.config_dir, "databases")
            if not os.path.isdir(connection_url):  # it doesn't exist
                try:
                    os.makedirs(connection_url)

                except Exception:
                    raise Exception(
                        "Cannot create directory %s for database", connection_url
                    )

            self.connection_url = f"sqlite:///{connection_url}"

        self.loop = self.AD.loop  # get AD loop

        self.database_metadata = {
            "version": "1.0",
            "connection_url": self.connection_url,
            "databases": self.databases,
            "tables": self.tables,
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
                    "Closing Database Connection to %s",
                    f"{self.connection_url}/{database}",
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
        if self.connection_url.startswith("sqlite:///"): #sqlite in use, so lock required
            self._lock = asyncio.Lock() # lock will be used to access the connection
        
        else:
            self._lock = None

        # set to continue
        self._event.set()

        while not self.stopping:
            await self._event.wait()
            while len(self.databases) != len(self.database_connections):
                # now create the connection to the databases, and store the connections
                for database in self.databases:
                    if database in self.database_connections:
                        continue

                    entity_id = f"database.{database.lower()}"
                    kwargs = {}
                    kwargs["attributes"] = {}

                    try:
                        if entity_id not in self.state:
                            kwargs["attributes"][
                                "friendly_name"
                            ] = f"{database.title()} Database"
                            kwargs["attributes"]["url"] = None

                        if self.connection_url.startswith("sqlite:///"):
                            database_url = os.path.join(
                                self.connection_url, f"{database}.db"
                            )
                            self.logger.debug(
                                "Creating connection to Database %s", database_url
                            )

                            self.database_connections[database] = Database(database_url)

                        else:
                            # first will need confirmation that the database exists, so attempt creating it
                            try:
                                async with Database(self.connection_url) as connection:
                                    await connection.execute(
                                        query=f"CREATE DATABASE IF NOT EXISTS {database}"
                                    )

                            except SQLERR.ProgrammingError as p:
                                if p.args[0] == 1007:  # it already exists
                                    self.logger.info(
                                        "Database %s already existing, so couldn't create it",
                                        database,
                                    )

                            database_url = f"{self.connection_url}/{database}"
                            self.logger.debug(
                                "Creating connection to Database %s", database_url
                            )

                            prams = {}
                            if self.ssl is not None:
                                prams["ssl"] = self.ssl

                            prams["min_size"] = 5
                            prams["max_size"] = self.connection_pool

                            self.database_connections[database] = Database(
                                database_url, **prams
                            )

                        await self.database_connections[database].connect()

                        self.logger.info(
                            "Connected to Database using URL %s", database_url
                        )

                        kwargs["state"] = "connected"
                        kwargs["attributes"]["url"] = database_url

                    except Exception as e:
                        if database in self.database_connections:
                            del self.database_connections[database]

                        self.logger.error("-" * 60)
                        self.logger.error(
                            "Could not setup connection to database %s", database_url
                        )
                        self.logger.error("-" * 60)
                        self.logger.error(e)
                        self.logger.debug(traceback.format_exc())
                        self.logger.error("-" * 60)

                        kwargs["state"] = "disconnected"

                    await self.state_update(entity_id, kwargs, not first_time)

                if len(self.database_connections) > 0:  # at least 1 of them connected
                    executed = True

                    if self.tables != {} and "appdaemon" in self.database_connections:
                        # need to setup entities database
                        # first we need to ensure we create the tables based on namespaces

                        for _namespace in self.tables:
                            if self.connection_url.startswith("sqlite:///"):
                                query = f"""CREATE TABLE IF NOT EXISTS {_namespace} (
                                        event_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
                                        event_type VARCHAR(100),
                                        entity_id VARCHAR(100), 
                                        data TEXT(10000), 
                                        timestamp TIMESTAMP)"""

                            else:
                                query = f"""CREATE TABLE IF NOT EXISTS {_namespace} (
                                        event_id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT, 
                                        event_type VARCHAR(100),
                                        entity_id VARCHAR(100), 
                                        data TEXT(10000), 
                                        timestamp TIMESTAMP)"""

                            executed = await self.database_execute(
                                "appdaemon", query, None
                            )

                            if executed is True:
                                await self.AD.events.add_event_callback(
                                    self.name,
                                    _namespace,
                                    self.event_callback,
                                    "state_changed",
                                    __silent=True,
                                    __namespace=_namespace,
                                )

                                if (
                                    self.tables[_namespace] is not None
                                    and "events" in self.tables[_namespace]
                                ):
                                    for event in self.tables[_namespace]["events"]:
                                        await self.AD.events.add_event_callback(
                                            self.name,
                                            _namespace,
                                            self.event_callback,
                                            event,
                                            __silent=True,
                                            __namespace=_namespace,
                                        )

                            else:  # it didn't create the table as requested
                                await self.database_connections[
                                    "appdaemon"
                                ].disconnect()
                                del self.database_connections["appdaemon"]
                                break

                    if (
                        executed is False
                    ):  # there  was an error when processing appdaemon table, so no need continuing processing
                        break

                    self.AD.services.register_service(
                        self.namespace, "database", "execute", self.call_plugin_service
                    )
                    self.AD.services.register_service(
                        self.namespace,
                        "database",
                        "fetch_one",
                        self.call_plugin_service,
                    )
                    self.AD.services.register_service(
                        self.namespace,
                        "database",
                        "fetch_all",
                        self.call_plugin_service,
                    )
                    self.AD.services.register_service(
                        self.namespace, "database", "create", self.call_plugin_service
                    )
                    self.AD.services.register_service(
                        self.namespace, "database", "drop", self.call_plugin_service
                    )
                    self.AD.services.register_service(
                        self.namespace,
                        "database",
                        "get_history",
                        self.call_plugin_service,
                    )
                    self.AD.services.register_service(
                        self.namespace, "server", "execute", self.call_plugin_service
                    )
                    self.AD.services.register_service(
                        self.namespace, "server", "fetch", self.call_plugin_service
                    )

                    states = await self.get_complete_state()

                    await self.AD.plugins.notify_plugin_started(
                        self.name,
                        self.namespace,
                        self.database_metadata,
                        states,
                        first_time,
                    )

                    first_time = False
                    already_notified = False

                elif len(self.database_connections) == 0 and already_notified is False:
                    await self.AD.plugins.notify_plugin_stopped(
                        self.name, self.namespace
                    )
                    already_notified = True

                if len(self.databases) != len(
                    self.database_connections
                ):  # some did not work
                    self.logger.warning(
                        "Could not connect to all Databases, will attempt in 5 seconds"
                    )

                elif len(self.databases) == len(
                    self.database_connections
                ):  # all initialized, so can wait
                    self._event.clear()  # it should stop

            await asyncio.sleep(5)

    #
    # Service Call
    #

    async def call_plugin_service(self, namespace, domain, service, kwargs):
        self.logger.debug(
            "call_plugin_service() namespace=%s domain=%s service=%s kwargs=%s",
            namespace,
            domain,
            service,
            kwargs,
        )
        res = None

        database = kwargs.get("database")
        query = kwargs.get("query")
        values = kwargs.get("values")

        if database is None and domain != "server":
            self.logger.warning(
                "Could not execute service call, as Database not provided"
            )
            return res

        elif query is None and service not in ["drop", "create"]:
            self.logger.warning("Could not execute service call, as Query not provided")
            return res

        if domain == "database":
            if service == "execute":
                asyncio.ensure_future(self.database_execute(database, query, values))

            elif service == "fetch_one":
                res = await self.database_fetch(database, query, values, "one")

            elif service == "fetch_all":
                res = await self.database_fetch(database, query, values, "all")

            elif service == "create":
                if database in self.databases:
                    self.logger.warning(
                        "Cannot create Database %s, as it already exists", database
                    )
                    return

                executed = await self.database_create(database, query)
                if executed is True:
                    self._event.set()  # continue to process connection

            elif service == "drop":
                if database not in self.databases:
                    self.logger.warning(
                        "Cannot drop Database %s, as it doesn't exists", database
                    )
                    return

                elif self.tables != {} and database == "appdaemon":
                    self.logger.warning(
                        "Cannot drop Database %s, as it used by AD", database
                    )
                    return

                try:
                    if not self.connection_url.startswith("sqlite:///"):
                        async with Database(self.connection_url) as connection:
                            await connection.execute(query=f"DROP DATABASE {database}")

                    else:
                        # its sqlite so just delete it
                        database_path = self.connection_url.replace("sqlite:///", "")
                        database_url = os.path.join(database_path, f"{database}.db")

                        if os.path.isfile(database_url):
                            os.remove(database_url)

                    await self.database_connections[database].disconnect()
                    del self.database_connections[database]
                    self.databases.remove(database)
                    entity_id = f"database.{database.title()}"
                    await self.AD.state.remove_entity(self.namespace, entity_id)
                    if entity_id in self.state:
                        del self.state[entity_id]

                    self.logger.info(
                        "Removal of the Database %s was successful", database
                    )

                except Exception as e:
                    self.logger.error("-" * 60)
                    self.logger.error("-" * 60)
                    self.logger.error(e)
                    self.logger.debug(traceback.format_exc())
                    self.logger.error("-" * 60)

            elif service == "get_history":
                return await self.get_history(**kwargs)

        elif domain == "server":
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

            except Exception as e:
                execute = False
                self.logger.error("-" * 60)
                self.logger.error("Could not create Database for %s", database)
                self.logger.error("-" * 60)
                self.logger.error(e)
                self.logger.debug(traceback.format_exc())
                self.logger.error("-" * 60)

        if executed is True:
            # now add it to the list, so the database is created
            if database not in self.databases:
                self.databases.append(database)

        return executed

    async def database_execute(self, database, query, values):
        """Used to execute a database query"""

        executed = False

        if self._lock is not None: # means sqlite used
            await self._lock.acquire()

        try:
            if database not in self.database_connections:
                self.logger.warning(
                    "Could not connect to Database %s, as no valid connection to it",
                    database,
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

            if (
                i.args[0] == 1049
            ):  # its an internal error. Possible connection lost so will need to be restarted
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
            if self._lock is not None: # means sqlite used
                self._lock.release()

        return executed

    async def database_fetch(self, database, query, values, rows="all"):
        """Used to fetch data from a database"""

        res = None

        if self._lock is not None: # means sqlite used
            await self._lock.acquire()

        try:
            if database not in self.database_connections:
                self.logger.warning(
                    "Could not connect to Database %s, as no valid connection to it",
                    database,
                )
                return res

            connection = self.database_connections[database]

            if rows == "all":
                res = await connection.fetch_all(query=query, values=values)

            else:
                res = await connection.fetch_one(query=query, values=values)

        except SQLERR.InternalError as i:
            self.logger.critical(i)

            if (
                i.args[0] == 1049
            ):  # its an internal error. Possible connection lost so will need to be restarted
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
            if self._lock is not None: # means sqlite used
                self._lock.release()

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
        days = kwargs.get("days")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        table = kwargs.get("table")

        # first process time interval of the request
        if days is None and start_time is None and end_time is None:  # nothing provided
            raise ValueError("Provided either days, start_time or end_time")

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

        if days is not None:
            # if starttime is declared and end_time is not declared, and days specified
            if start_time is not None and end_time is None:
                end_time = start_time + datetime.timedelta(days=days)

            # if endtime is declared and start_time is not declared, and days specified
            elif end_time is not None and start_time is None:
                start_time = end_time - datetime.timedelta(days=days)

            elif start_time is None and end_time is None:
                end_time = datetime.datetime.now()
                start_time = end_time - datetime.timedelta(days=days)

        if isinstance(table, str):
            table = table.split(",")

        elif table is None:
            list(self.tables.keys())

        for tab in table:
            r = {}  # story data
            tab = tab.strip()
            r[tab] = []
            values = {}
            query = f"SELECT * FROM {tab} "

            # decide if to get the
            if entity_id is not None:
                query = query + "WHERE entity_id = :entity_id "
                values["entity_id"] = entity_id

            elif event is not None:
                query = query + "WHERE event_type = :event "
                values["event"] = event

            if (
                "entity_id" not in values and "event" not in values
            ):  # one of them was seen
                values = None

            start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time = end_time.strftime("%Y-%m-%d %H:%M:%S")

            if "WHERE" in query:
                query = query + "AND "

            else:
                query = query + "WHERE "

            query = (
                query
                + f"timestamp BETWEEN '{start_time}' AND '{end_time}' ORDER BY timestamp"
            )
            results = await self.database_fetch("appdaemon", query, values)

            # now process result

            if results is not None:
                for result in results:
                    r[tab].append(json.loads(result[3]))

            res.append(r)

        return res

    async def event_callback(self, event, data, kwargs):
        self.logger.debug("event_callback: %s %s %s", kwargs, event, data)

        _namespace = kwargs["__namespace"]
        ts = await self.AD.sched.get_now()

        ts = ts.strftime("%Y-%m-%d %H:%M:%S")

        if event == "state_changed":
            entity_id = data["entity_id"]

            if _namespace not in self.tables or not self.store_entity(
                _namespace, entity_id
            ):
                return

            new_state = data["new_state"]
            del new_state["entity_id"]  # remove the entity_id, unnecessary data

            query = f"""INSERT INTO {_namespace}
                    (event_type, entity_id, data, timestamp) 
                    VALUES (:event_type, :entity_id, :data, :timestamp)"""

            values = {
                "event_type": "state_changed",
                "entity_id": entity_id,
                "data": json.dumps(new_state),
                "timestamp": ts,
            }

        else:
            query = f"""INSERT INTO {_namespace}
                    (event_type, data, timestamp) 
                    VALUES (:event_type, :data, :timestamp)"""

            values = {
                "event_type": event,
                "data": json.dumps(data),
                "timestamp": ts,
            }

        if self.stopping is False:
            asyncio.ensure_future(self.database_execute("appdaemon", query, values))

    def store_entity(self, namespace, entity_id):
        """Check if to store the entity's data"""

        execute = True

        if self.tables[namespace] is None:
            # there is no filers used for the namespace
            pass

        elif "exclude_domains" in self.tables[namespace]:
            excluded_domains = self.tables[namespace]["exclude_domains"]
            domain, _ = entity_id.split(".")

            if domain in excluded_domains:
                execute = False

        elif "include_domains" in self.tables[namespace]:
            included_domains = self.tables[namespace]["include_domains"]
            domain, _ = entity_id.split(".")

            if domain not in included_domains:
                execute = False

        elif "exclude_entities" in self.tables[namespace]:
            excluded_entities = self.tables[namespace]["exclude_entities"]

            if entity_id in excluded_entities:
                execute = False

        elif "inlude_entities" in self.tables[namespace]:
            included_entities = self.tables[namespace]["include_entities"]

            if entity_id not in included_entities:
                execute = False

        return execute

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
                    (await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz
                )  # possible AD isn"t ready at this point
            except:
                last_changed = None

            new_state["last_changed"] = last_changed

            if notified is True:  # AD had been updated of this namespace
                data = {
                    "event_type": "state_changed",
                    "data": {
                        "entity_id": entity_id,
                        "new_state": new_state,
                        "old_state": old_state,
                    },
                }

                await self.AD.events.process_event(
                    self.namespace, data
                )  # this is put ahead, to ensure integrity of the data. Breaks if not

            self.state[entity_id].update(new_state)

        except Exception as e:
            self.logger.error("-" * 60)
            self.logger.error("-" * 60)
            self.logger.error(e)
            self.logger.debug(traceback.format_exc())
            self.logger.error("-" * 60)
