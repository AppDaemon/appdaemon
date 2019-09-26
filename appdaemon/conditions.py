from abc import ABC, abstractmethod
import appdaemon.utils as utils
import datetime
import uuid

SEP_NAMESPACE = ":"
SEP_ATTRIBUTE = "#"

DEFAULT_OPERATOR = "=="
DEFAULT_VALUE = "on"
DEFAULT_ATTRIBUTE = "state"

DEFAULT_APP_NAME = "ctest"

ENTITY_NAMESPACE = "rules"
ENTITY_CLASS = "condition"


class ConditionManager:
    def __init__(self, AD):
        self.AD = AD
        self._condition_types = {}
        self._cancels = []

        self.register_condition_type('all', AllCondition)
        self.register_condition_type('any', AnyCondition)
        self.register_condition_type('state', StateCondition)
        self.register_condition_type('time', TimeCondition)
        self.register_condition_type('days', DaysCondition)

    def terminate(self):
        for cancel in self._cancels:
            cancel()

    def register_condition_type(self, name, cls):
        """Register a Condition

        Args:
            name: Name to reference the condition with
            cls: Class to implement the condition. Must be an extension of
                appdaemon.conditions.AbstractCondition

        Returns:
            None.
        """

        if name in self._condition_types:
            raise KeyError('Condition named {} already registered.'.format(
                name))

        self._condition_types[name] = cls

    def unregister_condition_type(self, name):
        """Unregister a Condition

        Args:
            name: Name to reference the condition with

        Returns:
            None.
        """

        if name not in self._condition_types:
            raise KeyError('Condition named {} not registered.'.format(
                name))

        del self._condition_types[name]

    def create_condition(self, condition_type, config):
        """Instantiate a Condition

        Args:
            condition_type: type of condition (as used in
                register_condition_type())
            config: the config to be sent to the condition.

        Returns:
            the Condition object (allowing for check() and listen() methods)
        """

        try:
            return self._condition_types[condition_type](self.AD, config)
        except KeyError:
            raise KeyError("{} is not a registered condition".format(
                condition_type))

    async def create_condition_entity(self, condition_type, config, name=None):
        """Create an entity for a condition

        Args:
            condition_type: type of condition (as used in
                register_condition_type())
            name: entity name to use for condition. If None a uuid will be
                created for you.

        Returns:
            entity_id of the condition entity
        """

        condition = self.create_condition(condition_type, config)
        return await self.create_entity_from_condition(condition, name)

    async def create_entity_from_condition(self, condition, name=None):
        if name is None:
            name = uuid.uuid4().hex

        entity_id = ENTITY_CLASS + '.' + name

        if await self.AD.state.entity_exists(ENTITY_NAMESPACE, entity_id):
            raise KeyError('entity already exists: {}'.format(entity_id))

        if not isinstance(condition, AbstractCondition):
            raise ValueError('entities can only be created from Conditions')

        def entity_callback(value, kwargs):
            pass
            # TODO add proper set_state code here
            # set_state(entity_id, state=value, namespace=ENTITY_NAMESPACE)

        self.cancels.append(await condition.listen(entity_callback))

        return entity_id


class AbstractCondition(ABC):

    # overwrite these methods
    @abstractmethod
    async def update(self):
        """Calculate the Condition Result

        Returns: boolean representing the condition evaluation
        """
        pass

    @abstractmethod
    async def setup_listener(self):
        """Setup Mechanism to Listen for changes

        This should establish a mechanism that either updates
        self.state with the boolean value of the condition
        or calls self.check() which will perform self.update()

        Returns: None
        """
        pass

    @abstractmethod
    async def destroy_listener(self):
        """Destroys resouces created by setup_listener()

        Returns: None
        """
        pass

    def initilaize(self):
        """Initalize any variables and parse configuration.

        Returns: None
        """
        pass

    # leave these methods
    def __init__(self, AD, config):
        self.name = DEFAULT_APP_NAME
        self.AD = AD
        self.listener = None
        self.__state = None

        self.config = config
        self.initialize()

    @property
    def state(self):
        """The current boolean state of the condition"""
        return self.__state

    @state.setter
    def state(self, new_state):
        if new_state != self.__state:
            self.__state = new_state
            self._fire_callback(new_state)

    @utils.sync_wrapper
    async def check(self):
        """Check the Condition and Return the result

        Returns: boolean
        """
        self.state = await self.update()
        return self.state

    @utils.sync_wrapper
    async def listen(self, cb, immediate=False, **kwargs):
        """Fire a Callback on change in Condition State

        Args:
            cb: the callback to be fired. it should have a signature
                of fn(value, kwargs)

        KWArgs:
            immediate: if True, the callback will fire immediately with the
                       state of the condition

            **:        any additional desired keywords to be sent to the
                       callback

        Returns: a function that, when called, will cancel the listener
        """
        self.listener = {
            "cb": cb,
            "kwargs": kwargs}

        await self.setup_listener()

        if immediate:
            await self.check()

        return self.cancel

    @utils.sync_wrapper
    async def cancel(self):
        """Cancels the established listener and destorys any resources.

        Returns: None
        """
        self.destory_listener()
        self.listener = None

    def _fire_callback(self, new_state):
        if self.listener is not None:
            self.listener['cb'](new_state, self.listener['kwargs'])


class TimeCondition(AbstractCondition):

    def initialize(self):
        self.cancel_handles = []
        self.times = self.parse_config()

    async def update(self):
        return await self.AD.sched.now_is_between(
            self.times['start'],
            self.times['end'],
            None)

    async def setup_listener(self):
        # get today
        now = await self.sched.get_now_naive()
        today = now.date()

        # make a start date time
        if type(self.times['start']) == datetime.time:
            when_start = self.times['start']
        elif type(self.times['start']) == str:
            parsed_start = await self.AD.sched._parse_time(
                self.times['start'], None)
            when_start = parsed_start['datetime'].time()
        else:
            raise ValueError("Invalid type for start")
        dt_start = datetime.datetime.combine(today, when_start)
        if dt_start < now:
            dt_start = dt_start + datetime.timedelta(days=1)

        # make an end date time
        if type(self.times['end']) == datetime.time:
            when_end = self.times['end']
        elif type(self.times['end']) == str:
            parsed_end = await self.AD.sched._parse_time(
                self.times['end'], None)
            when_end = parsed_end['datetime'].time()
        else:
            raise ValueError("Invalid type for end")
        dt_end = datetime.datetime.combine(today, when_end)
        if dt_end < now:
            dt_end = dt_start + datetime.timedelta(days=1)

        handle = await self.AD.sched.insert_schedule(
            self.name,
            dt_start,
            self.timer_callback,
            True,
            None,
            interval=24 * 60 * 60)
        self.cancel_handles.append(handle)

        handle = await self.AD.sched.insert_schedule(
            self.name,
            dt_end,
            self.timer_callback,
            True,
            None,
            interval=24 * 60 * 60)
        self.cancel_handles.append(handle)

    async def destroy_listener(self):
        while self.cancel_handles:
            cancel_handle = self.cancel_handles.pop()
            await self.AD.sched.cancel_timer(self.name, cancel_handle)

    # helping methods
    def parse_config(self):
        v = self.config
        if not isinstance(v, dict):
            raise ValueError('time condition must be a dict')

        if len(v) < 1 or len(v) > 2:
            raise ValueError(
                'time condition must contain only start and end keys')

        for key in v.keys():
            if key not in ['start', 'end']:
                raise ValueError(
                    '{} is not a valid key for time condition'.format(key))

        start_time = v.get('start', '00:00:00')
        end_time = v.get('end', '23:59:59')

        return {
            "start": start_time,
            "end": end_time
        }

    async def timer_callback(self, kwargs):
        await self.check()


class DaysCondition(AbstractCondition):
    # required methods
    def initialize(self):
        self.cancel_handles = []
        self.daylist = self.parse_config()

    async def update(self):
        now = await self.AD.sched.get_now_naive()
        if now.weekday() not in self.daylist:
            return False
        else:
            return True

    async def setup_listener(self):
        # get today
        now = await self.AD.sched.get_now_naive()
        today = now.date()

        # make a start date time
        when_start = datetime.time(hour=0, minute=0, second=1)
        dt_start = datetime.datetime.combine(today, when_start)
        if dt_start < now:
            dt_start = dt_start + datetime.timedelta(days=1)

        handle = await self.AD.sched.insert_schedule(
            self.name,
            dt_start,
            self.timer_callback,
            True,
            None,
            interval=24 * 60 * 60)
        self.cancel_handles.append(handle)

    async def destroy_listener(self):
        while self.cancel_handles:
            cancel_handle = self.cancel_handles.pop()
            await self.AD.sched.cancel_timer(self.name, cancel_handle)

    # helping methods
    async def timer_callback(self, kwargs):
        await self.check()

    def parse_config(self):
        ret = []
        for day in self.config.split(","):
            ret.append(utils.day_of_week(day))

        return ret


# class ConstraintCondition(AbstractCondition):

#     # required methods
#     def initialize(self):
#         pass

#     async def setup_listener(self):
#         raise Exception(
#             "A Constraint, '{}', cannot be listened to".format(
#                 self.config['name']
#             ))

#     async def destroy_listener(self):
#         raise Exception(
#             "A Constraint, '{}', cannot be cancelled".format(
#                 self.config['name']
#             ))

#     async def update(self):
#         fn = getattr(self.app, self.config['name'])
#         return fn(self.config['value'])


class AbstractLogicalCondition(AbstractCondition):

    # required methods
    def initialize(self):
        self.cancel_handles = []
        self.conditions = self.parse_config()

    @utils.sync_wrapper
    async def setup_listener(self):
        for c in self.conditions:
            handle = await c.listen(self.condition_callback)
            self.cancel_handles.append(handle)

    @utils.sync_wrapper
    async def destroy_listener(self):
        while self.cancel_handles:
            canceller = self.cancel_handles.pop()
            await canceller()

    # helping methods
    @utils.sync_wrapper
    async def condition_callback(self, state, kwargs):
        await self.check()

    def parse_config(self):
        ret = []
        c = self.config
        if not isinstance(c, list):
            raise ValueError('conditions must be a list of dicts')

        for c_one in c:
            if not isinstance(c_one, dict):
                raise ValueError('each condition must be a dict')

            if len(c_one) != 1:
                raise ValueError('each dict must contain only one key')

            condition_name = list(c_one.keys())[0]
            condition_parameter = c_one[condition_name]

            cond_obj = self.AD.conditions.create_condition(
                condition_name,
                condition_parameter)

            ret.append(cond_obj)

        return ret


class AnyCondition(AbstractLogicalCondition):
    async def update(self):
        ret = False

        for c in self.conditions:
            ret = await c.check()
            if ret is None:
                return None
            if ret is True:
                return True

        return ret


class AllCondition(AbstractLogicalCondition):
    async def update(self):
        if len(self.conditions) == 0:
            ret = False
        else:
            ret = True

        for c in self.conditions:
            ret = await c.check()
            if ret is None:
                return None
            if ret is False:
                return False

        return ret


class StateCondition(AbstractCondition):

    # required methods
    def initialize(self):
        pc = self.parse_condition()
        self.entity = pc['entity_id']
        self.operator = pc['operator']
        self.value = pc['value']

        self.handle = False

    async def update(self):
        entity_value = await self.AD.state.get_state(
            self.name,
            self.entity['namespace'],
            self.entity['entity_id'],
            self.entity['attribute'],
            None,
            True)

        return self.compare_value(
            entity_value, self.operator, self.value)

    async def setup_listener(self):
        self.handle = await self.AD.state.add_state_callback(
            self.name,
            self.entity['namespace'],
            self.entity['entity_id'],
            self.state_callback,
            {})

    async def destroy_listener(self):
        await self.AD.state.cancel_state_callback(self.handle, self.name)
        self.handle = None

    # helping methods
    async def state_callback(self, entity, attribute, new, old, kwargs):
        await self.check()

    def compare_value(self, state, operator, value):
        try:
            if operator == "==":
                ret = state == value

            elif operator == ">=":
                ret = float(state) >= float(value)

            elif operator == ">":
                ret = float(state) > float(value)

            elif operator == "<=":
                ret = float(state) <= float(value)

            elif operator == "<":
                ret = float(state) < float(value)

            elif operator == "!=":
                ret = state != value

            else:
                return None
        except ValueError:
            return None
        except TypeError:
            return None

        return ret

    def parse_condition(self):
        c = self.config
        if isinstance(c, str):
            c_dict = self.parse_condition_string(c)
        elif isinstance(c, dict):
            c_dict = c
        else:
            raise ValueError('condition must be str or dict')

        if isinstance(c_dict['entity_id'], str):
            c_dict['entity_id'] = self.parse_entity_id_string(
                c_dict['entity_id'])
        elif isinstance(c_dict['entity_id'], dict):
            pass
        else:
            raise ValueError('entity_id must be str or dict')

        self.validate_condition(c_dict)

        return c_dict

    def parse_condition_string(self, c_str):
        r = {}
        pieces = c_str.split(" ", 2)
        if len(pieces) == 3:
            r['entity_id'] = pieces[0]
            r['operator'] = pieces[1]
            r['value'] = pieces[2]
        elif len(pieces) == 2:
            r['entity_id'] = pieces[0]
            r['operator'] = DEFAULT_OPERATOR
            r['value'] = pieces[1]
        else:
            r['entity_id'] = pieces[0]
            r['operator'] = DEFAULT_OPERATOR
            r['value'] = DEFAULT_VALUE

        return r

    def parse_entity_id_string(self, e_str):
        r = {
            "namespace": 'default',
            "entity_id": None,
            "attribute": DEFAULT_ATTRIBUTE,
        }

        try:
            index = e_str.index(SEP_NAMESPACE, 0)
            r['namespace'] = e_str[0:index]
            e_str = e_str[(index+len(SEP_NAMESPACE)):]
        except ValueError:
            pass

        try:
            index = e_str.index(SEP_ATTRIBUTE, 0)
            r['attribute'] = e_str[(index+len(SEP_ATTRIBUTE)):]
            e_str = e_str[0:index]
        except ValueError:
            pass

        r['entity_id'] = e_str

        return r

    def validate_condition(self, c_dict):
        if not isinstance(c_dict, dict):
            raise ValueError('condition must be dict')

        for key in ['entity_id', 'operator', 'value']:
            if key not in c_dict:
                raise ValueError('dict is missing key: {}'.format(key))

        if len(c_dict) != 3:
            raise ValueError(
                'extra keys are present in dict')

        e_dict = c_dict['entity_id']

        if not isinstance(e_dict, dict):
            raise ValueError('entity_id must be dict')

        for key in ['entity_id', 'namespace', 'attribute']:
            if key not in e_dict:
                raise ValueError(
                    'entity_id dict is missing key: {}'.format(key))

        if len(e_dict) != 3:
            raise ValueError(
                'extra keys are present in entity_id dict')

        return
