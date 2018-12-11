import asyncio
import datetime
import traceback

import appdaemon.scheduler as scheduler
import appdaemon.utils as utils
from appdaemon.appdaemon import AppDaemon


class Utility:

    def __init__(self, ad: AppDaemon):

        self.AD = ad
        self.stopping = False
        self.logger = ad.logging.get_child("_utility")

    def stop(self):
        self.logger.debug("stop() called for utility")
        self.stopping = True

    async def loop(self):

        #
        # Setup
        #

        await self.AD.threading.init_admin_stats()
        await self.AD.threading.create_initial_threads()


        #
        # Wait for all plugins to initialize
        #

        await self.AD.plugins.wait_for_plugins()

        # Check if we need to bail due to missing metadata

        if self.AD.plugins.required_meta_check() is False:
            if self.AD.stop_function is not None:
                self.AD.stop_function()
            else:
                self.stop()

        if not self.stopping:

            #
            # All plugins are loaded and we have initial state
            # We also have metadata so we can initialise the scheduler
            #

            self.AD.sched = scheduler.Scheduler(self.AD)

            if self.AD.apps is True:
                self.logger.debug("Reading Apps")

                await self.AD.app_management.check_app_updates()

                self.logger.info("App initialization complete")
                #
                # Fire APPD Started Event
                #
                await self.AD.events.process_event("global", {"event_type": "appd_started", "data": {}})

            # Create timer loop

            self.logger.debug("Starting timer loop")

            self.AD.loop.create_task(self.AD.sched.do_every())

            self.booted = self.AD.sched.get_now()
            await self.AD.state.add_entity("admin", "sensor.appdaemon_version", utils.__version__)
            await self.AD.state.add_entity("admin", "sensor.appdaemon_uptime", str(datetime.timedelta(0)))
            await self.AD.state.add_entity("admin", "sensor.appdaemon_booted", self.AD.sched.make_naive(self.booted.replace(microsecond=0)).isoformat())

            warning_step = 0
            warning_iterations = 0

            # Start the loop proper

            while not self.stopping:

                start_time = datetime.datetime.now().timestamp()

                try:

                    if self.AD.apps is True:

                        if self.AD.production_mode is False:
                            # Check to see if config has changed
                            await self.AD.app_management.check_app_updates()


                    # Call me suspicious, but lets update state from the plugins periodically
                    # in case we miss events for whatever reason
                    # Every 10 minutes seems like a good place to start

                    await self.AD.plugins.update_plugin_state()

                    # Check for thread starvation

                    warning_step, warning_iterations = self.AD.threading.check_q_size(warning_step, warning_iterations)

                    # Check for any overdue threads

                    self.AD.threading.check_overdue_and_dead_threads()

                    # Save any hybrid namespaces

                    self.AD.state.save_hybrid_namespaces()

                    # Run utility for each plugin

                    self.AD.plugins.run_plugin_utility()

                    # Update uptime sensor

                    uptime = self.AD.sched.get_now().replace(microsecond=0) - self.booted.replace(microsecond=0)
                    await self.AD.state.set_state("_utility", "admin", "sensor.appdaemon_uptime", state=str(uptime))

                except:
                    self.logger.warning('-' * 60)
                    self.logger.warning("Unexpected error during utility()")
                    self.logger.warning('-' * 60)
                    self.logger.warning(traceback.format_exc())
                    self.logger.warning('-' * 60)

                end_time = datetime.datetime.now().timestamp()

                loop_duration = (int((end_time - start_time) * 1000) / 1000) * 1000

                self.logger.debug("Util loop compute time: %sms", loop_duration)
                if self.AD.sched.realtime is True and loop_duration > (self.AD.max_utility_skew * 1000):
                    self.logger.warning("Excessive time spent in utility loop: %sms", loop_duration)
                    if self.AD.check_app_updates_profile is True:
                        self.logger.info("Profile information for Utility Loop")
                        self.logger.info(self.AD.app_management.check_app_updates_profile_stats)

                await asyncio.sleep(self.AD.utility_delay)

            if self.AD.app_management is not None:
                await self.AD.app_management.terminate()
