import hassapi as hass
import datetime
import re
import random
import globals

#
# App to simulate occupancy in an empty house
#

__version__ = "1.1.2"


class OccuSim(hass.Hass):
    def initialize(self):

        if "test" in self.args and self.args["test"] == "1":
            self.test = True
        else:
            self.test = False

        self.timers = ()

        # Set a timer to recreate the day's events at 3am
        if "reset_time" in self.args:
            time = self.parse_time(self.args["reset_time"])
        else:
            time = datetime.time(3, 0, 0)
        self.run_daily(self.create_events, time)

        # Create today's random events
        self.create_events({})

    def create_events(self, kwargs):  # noqa: C901
        # self.log_notify("Running Create Events")

        events = {}
        steps = ()
        randoms = ()

        for arg in self.args:
            m = re.search("step_(.+)_name", arg)
            if m:
                steps = steps + (m.group(1),)
            m = re.search("random_(.+)_name", arg)
            if m:
                randoms = randoms + (m.group(1),)

        # First pick up absolute events
        for step in steps:
            event = None
            step = "step_" + step + "_"
            if (step + "start") in self.args:
                stepname = self.args[step + "name"]
                cbargs = {"step": stepname}
                if (step + "days") in self.args:
                    cbargs["days"] = self.args[step + "days"]
                span = 0
                for arg in self.args:
                    if re.match(step + "on", arg) or re.match(step + "off", arg):
                        cbargs[arg] = self.args[arg]

                start_p = self.args[step + "start"]
                start = self.parse_time(start_p)
                end_p = self.args.get(step + "end")
                if end_p is not None:
                    end = self.parse_time(end_p)
                    start_ts = datetime.datetime.combine(self.date(), start).timestamp()
                    end_ts = datetime.datetime.combine(self.date(), end).timestamp()
                    span = int(end_ts - start_ts)
                if span > 0:
                    event = datetime.datetime.combine(self.date(), start) + datetime.timedelta(
                        seconds=random.randrange(span)
                    )
                elif span == 0:
                    event = datetime.datetime.combine(self.date(), start)
                elif span < 0:
                    self.log("step_{} end < start - ignoring end".format(step))
                    event = datetime.datetime.combine(self.date(), start)

                events[stepname] = {}
                events[stepname]["event"] = event
                events[stepname]["args"] = cbargs.copy()

        # Now relative events - multiple passes required as the order could be arbitrary

        changes = 1

        while changes > 0:
            changes = 0
            for step in steps:
                event = None
                step = "step_" + step + "_"
                if (step + "relative") in self.args:
                    stepname = self.args[step + "name"]
                    if stepname not in events:
                        cbargs = {"step": stepname}
                        if (step + "days") in self.args:
                            cbargs["days"] = self.args[step + "days"]
                        span = 0
                        for arg in self.args:
                            if re.match(step + "on", arg) or re.match(step + "off", arg):
                                cbargs[arg] = self.args[arg]

                        steprelative = self.args[step + "relative"]
                        if steprelative in events:
                            start_offset_p = self.args[step + "start_offset"]
                            start_offset = self.parse_time(start_offset_p)
                            start = events[steprelative]["event"] + datetime.timedelta(
                                hours=start_offset.hour,
                                minutes=start_offset.minute,
                                seconds=start_offset.second,
                            )
                            end_offset_p = self.args.get(step + "end_offset")
                            if end_offset_p is not None:
                                end_offset = self.parse_time(end_offset_p)
                                end = events[steprelative]["event"] + datetime.timedelta(
                                    hours=end_offset.hour,
                                    minutes=end_offset.minute,
                                    seconds=end_offset.second,
                                )
                                span = int(end.timestamp() - start.timestamp())
                            if span > 0:
                                event = start + datetime.timedelta(seconds=random.randrange(span))
                            elif span == 0:
                                event = start
                            elif span < 0:
                                self.log("step_{} end < start - ignoring end".format(step))
                                event = start

                            events[stepname] = {}
                            events[stepname]["event"] = event
                            events[stepname]["args"] = cbargs.copy()
                            changes += 1

        list = ""
        for step in steps:
            stepname = self.args["step_" + step + "_name"]
            if stepname not in events:
                list += stepname + " "

        if list != "":
            self.log(
                "unable to schedule the following steps due to missing prereq step: {}".format(list),
                "WARNING",
            )

        # Schedule random events

        for step in randoms:
            event = None
            step = "random_" + step + "_"
            stepname = self.args[step + "name"]
            cbonargs = {}
            cboffargs = {}
            if (step + "days") in self.args:
                cbonargs["days"] = self.args[step + "days"]
                cboffargs["days"] = self.args[step + "days"]

            span = 0
            for arg in self.args:
                if re.match(step + "on", arg):
                    cbonargs[arg] = self.args[arg]
                if re.match(step + "off", arg):
                    cboffargs[arg] = self.args[arg]

            startstep = self.args[step + "start"]
            endstep = self.args[step + "end"]
            starttime = events[startstep]["event"]
            endtime = events[endstep]["event"]
            tspan = int(endtime.timestamp() - starttime.timestamp())

            mind_p = self.args[step + "minduration"]
            mind = self.parse_time(mind_p)
            maxd_p = self.args[step + "maxduration"]
            maxd = self.parse_time(maxd_p)
            dspan = int(
                datetime.datetime.combine(self.date(), maxd).timestamp()
                - datetime.datetime.combine(self.date(), mind).timestamp()
            )

            for i in range(int(self.args[step + "number"])):
                start = starttime + datetime.timedelta(seconds=random.randrange(tspan))
                end = start + datetime.timedelta(seconds=random.randrange(dspan))
                if end > endtime:
                    end = endtime

                eventname = stepname + "_on_" + str(i)
                events[eventname] = {}
                events[eventname]["event"] = start
                cbonargs["step"] = eventname
                events[eventname]["args"] = cbonargs.copy()

                eventname = stepname + "_off_" + str(i)
                events[eventname] = {}
                events[eventname]["event"] = end
                cboffargs["step"] = eventname
                events[eventname]["args"] = cboffargs.copy()

        # Take all the events we found and schedule them

        for event in sorted(events.keys(), key=lambda event: events[event]["event"]):
            stepname = events[event]["args"]["step"]
            start = events[event]["event"]
            args = events[event]["args"]
            if start > self.datetime():
                # schedule it
                if "enable" in self.args:
                    args["constrain_input_boolean"] = self.args["enable"]
                if "days" in events[event]["args"]:
                    args["constrain_days"] = events[event]["args"]["days"]
                self.run_at(self.execute_step, start, **args)
                if "dump_times" in self.args:
                    self.log("{}: @ {}".format(stepname, start))
            else:
                self.log("{} in the past - ignoring".format(stepname))

    def execute_step(self, kwargs):
        # Set the house up for the specific step
        self.step = kwargs["step"]
        self.log_notify("Executing step {}".format(self.step))
        for arg in kwargs:
            if re.match(".+on.+", arg):
                self.activate(kwargs[arg], "on")
            elif re.match(".+off.+", arg):
                self.activate(kwargs[arg], "off")

    def activate(self, entity, action):
        type = action
        m = re.match(r"event\.(.+)\,(.+)", entity)
        if m:
            if not self.test:
                self.fire_event(m.group(1), **{m.group(2): self.step})
            if "verbose_log" in self.args:
                self.log("fired event {} with {} = {}".format(m.group(1), m.group(2), self.step))
            return
        m = re.match(r"input_select\.", entity)
        if m:
            if not self.test:
                self.select_option(entity, self.step)
            self.log("set {} to value {}".format(entity, self.step))
            return
        if action == "on":
            if not self.test:
                self.turn_on(entity)
        else:
            if re.match(r"scene\.", entity):
                type = "on"
                if not self.test:
                    self.turn_on(entity)
            else:
                if not self.test:
                    self.turn_off(entity)

        if "verbose_log" in self.args:
            self.log("turned {} {}".format(type, entity))

    def log_notify(self, message):
        if "verbose_log" in self.args:
            self.log(message)
        if "notify" in self.args:
            self.notify(message, name=globals.notify)
