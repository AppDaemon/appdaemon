"""Module to handle utility functions within AppDaemon."""

import asyncio
import datetime
import traceback

import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon


class Utility:

    """Class that includes the utility loop.

    Checks for file changes, overdue threads, thread starvation, and schedules regular state refreshes.
    """

    def __init__(self, ad: AppDaemon):
        """Constructor.

        Args:
            ad: Reference to the AppDaemon object
        """

        self.AD = ad
        self.stopping = False
        self.logger = ad.logging.get_child("_utility")
        self.booted = None

    def stop(self):
        """Called by the AppDaemon object to terminate the loop cleanly

        Returns:
            None

        """

        self.logger.debug("stop() called for utility")
        self.stopping = True

    async def loop(self):
        """The main utility loop.

        Loops until stop() is called, checks for file changes, overdue threads, thread starvation,
        and schedules regular state refreshes.
        """

        #
        # Setup
        #

        await self.AD.threading.init_admin_stats()
        await self.AD.threading.create_initial_threads()
        await self.AD.app_management.init_admin_stats()

        #
        # Start the web server
        #

        if self.AD.http is not None:
            await self.AD.http.start_server()

        #
        # Wait for all plugins to initialize
        #

        await self.AD.plugins.wait_for_plugins()

        if not self.stopping:

            # Create timer loop

            self.logger.debug("Starting timer loop")

            for ns in await self.AD.state.list_namespaces():

                #
                # Register state services
                #

                # only default, rules or it belongs to a local plugin. Don't allow for admin/appdaemon/global namespaces

                if ns in ["default", "rules"] or ns in self.AD.plugins.plugin_objs or ns in self.AD.namespaces:
                    self.AD.services.register_service(ns, "state", "add_namespace", self.AD.state.state_services)
                    self.AD.services.register_service(ns, "state", "add_entity", self.AD.state.state_services)
                    self.AD.services.register_service(ns, "state", "set", self.AD.state.state_services)
                    self.AD.services.register_service(ns, "state", "remove_namespace", self.AD.state.state_services)
                    self.AD.services.register_service(ns, "state", "remove_entity", self.AD.state.state_services)

                #
                # Register fire_event services
                #

                self.AD.services.register_service(ns, "event", "fire", self.AD.events.event_services)

            #
            # Register run_sequence service
            #
            self.AD.services.register_service("rules", "sequence", "run", self.AD.sequences.run_sequence_service)

            #
            # Register production_mode service
            #
            self.AD.services.register_service("appdaemon", "production_mode", "set", self.production_mode_service)

            #
            # Register logging services
            #
            self.AD.services.register_service("appdaemon", "logs", "get_admin", self.AD.logging.manage_services)

            #
            # Start the scheduler
            #
            self.AD.loop.create_task(self.AD.sched.loop())

            if self.AD.apps is True:
                self.logger.debug("Reading Apps")

                await self.AD.app_management.check_app_updates(mode="init")

                self.logger.info("App initialization complete")
                #
                # Fire APPD Started Event
                #
                await self.AD.events.process_event("global", {"event_type": "appd_started", "data": {}})

            self.booted = await self.AD.sched.get_now()
            await self.AD.state.add_entity("admin", "sensor.appdaemon_version", utils.__version__)
            await self.AD.state.add_entity("admin", "sensor.appdaemon_uptime", str(datetime.timedelta(0)))
            await self.AD.state.add_entity(
                "admin",
                "sensor.appdaemon_booted",
                utils.dt_to_str((await self.AD.sched.get_now()).replace(microsecond=0), self.AD.tz),
            )
            warning_step = 0
            warning_iterations = 0
            s1 = 0
            e1 = 0

            # Start the loop proper

            while not self.stopping:

                start_time = datetime.datetime.now().timestamp()

                try:

                    if self.AD.apps is True:

                        if self.AD.production_mode is False:
                            # Check to see if config has changed
                            s1 = datetime.datetime.now().timestamp()
                            await self.AD.app_management.check_app_updates()
                            e1 = datetime.datetime.now().timestamp()

                    # Call me suspicious, but lets update state from the plugins periodically

                    await self.AD.plugins.update_plugin_state()

                    # Check for thread starvation

                    (warning_step, warning_iterations,) = await self.AD.threading.check_q_size(
                        warning_step, warning_iterations
                    )

                    # Check for any overdue threads

                    await self.AD.threading.check_overdue_and_dead_threads()

                    # Save any hybrid namespaces

                    self.AD.state.save_hybrid_namespaces()

                    # Run utility for each plugin

                    self.AD.plugins.run_plugin_utility()

                    # Update uptime sensor

                    uptime = (await self.AD.sched.get_now()).replace(microsecond=0) - self.booted.replace(microsecond=0)

                    await self.AD.state.set_state(
                        "_utility", "admin", "sensor.appdaemon_uptime", state=str(uptime),
                    )

                except Exception:
                    self.logger.warning("-" * 60)
                    self.logger.warning("Unexpected error during utility()")
                    self.logger.warning("-" * 60)
                    self.logger.warning(traceback.format_exc())
                    self.logger.warning("-" * 60)

                end_time = datetime.datetime.now().timestamp()

                loop_duration = (int((end_time - start_time) * 1000) / 1000) * 1000
                check_app_updates_duration = (int((e1 - s1) * 1000) / 1000) * 1000

                self.logger.debug(
                    "Util loop compute time: %sms, check_config()=%sms, other=%sms",
                    loop_duration,
                    check_app_updates_duration,
                    loop_duration - check_app_updates_duration,
                )
                if self.AD.sched.realtime is True and loop_duration > (self.AD.max_utility_skew * 1000):
                    self.logger.warning(
                        "Excessive time spent in utility loop: %sms, %sms in check_app_updates(), %sms in other",
                        loop_duration,
                        check_app_updates_duration,
                        loop_duration - check_app_updates_duration,
                    )
                    if self.AD.check_app_updates_profile is True:
                        self.logger.info("Profile information for Utility Loop")
                        self.logger.info(self.AD.app_management.check_app_updates_profile_stats)

                await asyncio.sleep(self.AD.utility_delay)

            #
            # Shutting down now
            #

            #
            # Stop apps
            #
            if self.AD.app_management is not None:
                await self.AD.app_management.terminate()

            #
            # Shutdown webserver
            #

            if self.AD.http is not None:
                await self.AD.http.stop_server()

    async def set_production_mode(self, mode=True):
        if mode is True:
            self.logger.info("AD Production Mode Activated")
        else:
            self.logger.info("AD Production Mode Deactivated")
        self.AD.production_mode = mode

    async def production_mode_service(self, ns, domain, service, kwargs):
        if "mode" in kwargs:
            mode = kwargs["mode"]
            await self.set_production_mode(mode)
        else:
            self.logger.warning("'Mode' not specified in service call")
