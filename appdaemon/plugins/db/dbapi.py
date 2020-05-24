import appdaemon.adbase as adbase
import appdaemon.adapi as adapi
from appdaemon.appdaemon import AppDaemon
import appdaemon.utils as utils


class Db(adbase.ADBase, adapi.ADAPI):

    # entities = Entities()

    def __init__(
        self, ad: AppDaemon, name, logging, args, config, app_config, global_vars,
    ):

        # Call Super Classes
        adbase.ADBase.__init__(
            self, ad, name, logging, args, config, app_config, global_vars
        )
        adapi.ADAPI.__init__(
            self, ad, name, logging, args, config, app_config, global_vars
        )

    #
    # Helper Functions
    #

    @utils.sync_wrapper
    async def get_history(self, **kwargs):
        """Gets access to the AD's Database.
        This is a convenience function that allows accessing the AD's Database, so the
        history state of a device can be retrieved. It allows for a level of flexibility
        when retrieving the data, and returns it as a dictionary list. Caution must be
        taken when using this, as depending on the size of the database, it can take
        a long time to process. This function only works when using the ``appdaemon`` database
        Args:
            **kwargs (optional): Zero or more keyword arguments.
        Keyword Args:
            entity_id (str, optional): Fully qualified id of the device to be querying, e.g.,
                ``mqtt.office_lamp`` or ``sequence.ligths_on`` This can be any entity_id
                in the database. If this is left empty, the state of all entities will be
                retrieved within the specified time.
            event (str, optional): The event type to be querying, e.g., ``zwave``, ``mqtt``
                This can be any event in the database. If this is left empty, and no entity_id supplied
                the state of all entities and events will be retrieved within the specified time.
                If ``entity_id`` is specified alonside the ``event``,  the ``event`` will be ignored.
            table (str | list, optional): The table to get the data from, which corresponds to the namespaces the data is 
                to be retrieved from e.g. ``hass``. If not specified, AD will attempt to get the data from all
                the tables. For example getting data on the entity_id ``sensor.time``, if ``table`` not specified
                it will get data from all tables (namespaces) that might have entity_id ``sensor.time``.
                This accepts a list, or comma serparated string.
            days (int, optional): The days from the present-day walking backwards that is
                required from the database. Either days, start_time or end_time must be defined.
            start_time (str | datetime, optional): The start time from when the data should be retrieved.
                This should be the furthest time backwards, like if we wanted to get data from
                now until two days ago. Your start time will be the last two days datetime.
                ``start_time`` time can be either a UTC aware time string like ``2019-04-16 12:00:03+01:00``
                or a ``datetime.datetime`` object. Either days, start_time or end_time must be defined.
            end_time (str | datetime, optional): The end time from when the data should be retrieved. This should
                be the latest time like if we wanted to get data from now until two days ago. Your
                end time will be today's datetime ``end_time`` time can be either a UTC aware time
                string like ``2019-04-16 12:00:03+01:00`` or a ``datetime.datetime`` object. It should
                be noted that it is not possible to declare only ``end_time``. If only ``end_time``
                is declared without ``start_time`` or ``days``, it will revert to default to the latest
                history state. Either days, start_time or end_time must be defined.
            callback (callable, optional): If wanting to access the database to get a large amount of data,
                using a direct call to this function will take a long time to run and lead to AD cancelling the task.
                To get around this, it is better to pass a function, which will be responsible of receiving the result
                from the database. The signature of this function follows that of a scheduler call.
            namespace (str, optional): Namespace to use for the call, which which the database is functioning. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
        Returns:
            An iterable list of entity_ids/events and their history.

        Examples:
            Get device state over the last 5 days.
            >>> data = self.get_history(entity_id="light.office_lamp", days = 5)
            Get device zwave data over the last 2 days and walk forward.
            >>> import datetime
            >>> from datetime import timedelta
            >>> start_time = datetime.datetime.now() - timedelta(days = 2)
            >>> data = self.get_history(event="zwave", start_time=start_time)
            Get event data from the hass and mqtt namespaces over the past 5 days.
            >>> import datetime
            >>> from datetime import timedelta
            >>> start_time = datetime.datetime.now() - timedelta(days=5)
            >>> data = self.get_history(event="zwave", start_time=start_time, days=5, table="hass,mqtt")
            Get all data from yesterday and walk 5 days back.
            >>> import datetime
            >>> from datetime import timedelta
            >>> end_time = datetime.datetime.now() - timedelta(days = 1)
            >>> data = self.get_history(end_time=end_time, days = 5)
        """

        namespace = self._get_namespace(**kwargs)
        plugin = await self.AD.plugins.get_plugin_object(namespace)

        if hasattr(plugin, "get_history"):
            callback = kwargs.pop("callback", None)
            if callback is not None and callable(callback):
                self.create_task(plugin.get_history(**kwargs), callback)
                
            else:
                return await plugin.get_history(**kwargs)

        else:
            self.logger.warning(
                "Wrong Namespace selected, as %s has no database plugin attached to it",
                namespace,
            )
            return None

    @utils.sync_wrapper
    async def database_execute(self, database, query, **kwargs):
        """Executes a query against a defined Database. 
        This is a convenience function that allows accessing and executing a query against
        a database AD has access to. This database must be valid,  and must have been created 
        prior to accessing.
        Args:
            database (str): The database to be accessed
            query (str): A valid SQL query command, to be executed against the database            
            **kwargs (optional): Zero or more keyword arguments.
        Keyword Args:
            values (dict|list): Values to be executed alongside the query command. This must follow the
            same syntax as defined here https://www.encode.io/databases/
            namespace (str, optional): Namespace to use for the call, which which the database is functioning. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
        Returns:
            None

        Examples:
            Create a table in a predefined database
            >>> query = "CREATE TABLE shopping_list (id INTEGER PRIMARY KEY AUTOINCREMENT, item VARCHAR, Day DATE)"
            >>> self.databse_execute("home", query)
        """

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        await self.call_service(
            "database/execute",
            databse=database,
            query=query,
            namespace=namespace,
            **kwargs
        )

        return None

    @utils.sync_wrapper
    async def database_fetch_one(self, database, query, **kwargs):
        """Executes a query against a defined Database, to get a single row of data.
        This is a convenience function that allows accessing data from a databse using a query. 
        This database must be valid,  and must have been created pior to accessing.
        Args:
            database (str): The database to be accessed
            query (str): A valid SQL query command, to be used to fetch the data against the database            
            **kwargs (optional): Zero or more keyword arguments.
        Keyword Args:
            values (dict): Values to be executed alongside the query command. This must follow the
            same syntax as defined here https://www.encode.io/databases/
            namespace (str, optional): Namespace to use for the call, which which the database is functioning. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
        Returns:
            list of data

        Examples:
            Get the first role of data of an entity_id
            >>> query = "SELECT * FROM shopping_list WHERE item = :item ORDER id"
            >>> values = {"item" : "milk"}
            >>> row = self.databse_fetch_one("home", query, values=values)
        """

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        return await self.call_service(
            "database/fetch_one",
            database=database,
            query=query,
            namespace=namespace,
            **kwargs
        )

    @utils.sync_wrapper
    async def database_fetch_all(self, database, query, **kwargs):
        """Executes a query against a defined Database, to get all rows of data.
        This is a convenience function that allows accessing data from a databse using a query. 
        This database must be valid,  and must have been created pior to accessing.
        Args:
            database (str): The database to be accessed
            query (str): A valid SQL query command, to be used to fetch the data against the database            
            **kwargs (optional): Zero or more keyword arguments.
        Keyword Args:
            values (dict): Values to be executed alongside the query command. This must follow the
            same syntax as defined here https://www.encode.io/databases/
            namespace (str, optional): Namespace to use for the call, which which the database is functioning. See the section on
                `namespaces <APPGUIDE.html#namespaces>`__ for a detailed description.
                In most cases it is safe to ignore this parameter.
        Returns:
            list of data

        Examples:
            Get the first role of data of an entity_id
            >>> query = "SELECT * FROM shopping_list WHERE item = :item ORDER id"
            >>> values = {"item" : "milk"}
            >>> row = self.databse_fetch_all("home", query, values=values)
        """

        namespace = self._get_namespace(**kwargs)
        if "namespace" in kwargs:
            del kwargs["namespace"]

        return await self.call_service(
            "database/fetch_all",
            database=database,
            query=query,
            namespace=namespace,
            **kwargs
        )
