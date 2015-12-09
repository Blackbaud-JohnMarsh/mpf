import unittest

from mpf.system.machine import MachineController
from mpf.system.utility_functions import Util
import logging
import time
import sys
from mock import *
from datetime import datetime, timedelta
import inspect

# TODO: mock BCP and prevent logs

class TestMachineController(MachineController):

    def __init__(self, options, config_patches):
        self.test_config_patches = config_patches
        super(TestMachineController, self).__init__(options)

    def _load_machine_config(self):
        super(TestMachineController, self)._load_machine_config()
        self.config = Util.dict_merge(self.config, self.test_config_patches,
                                      combine_lists=False)
        # print self.config['plugins']


class MpfTestCase(unittest.TestCase):

    machine_config_patches = dict()
    machine_config_patches['mpf'] = dict()
    machine_config_patches['mpf']['save_machine_vars_to_disk'] = False
    machine_config_patches['mpf']['plugins'] = list()

    def get_platform(self):
        return 'virtual'

    def get_use_bcp(self):
        return False

    def getOptions(self):
        return {
            'force_platform': self.get_platform(),
            'mpfconfigfile': "mpf/mpfconfig.yaml",
            'machine_path': self.getMachinePath(),
            'configfile': Util.string_to_list(self.getConfigFile()),
            'debug': True,
            'bcp': self.get_use_bcp()
               }

    def set_time(self, new_time):
        self.testTime = new_time
        time.time.return_value = self.testTime

    def advance_time(self, delta):
        self.testTime += delta
        time.time.return_value = self.testTime

    def advance_time_and_run(self, delta):
        end_time = time.time() + delta
        self.machine.log.debug("Advance until %s", end_time)
        self.machine_run()
        while True:
            next_event = self.machine.delayRegistry.get_next_event()
            next_timer = self.machine.timing.get_next_timer()
            next_switch = self.machine.switch_controller.get_next_timed_switch_event()

            wait_until = next_event
            if not wait_until or (next_timer and wait_until > next_timer):
                wait_until = next_timer

            if not wait_until or (next_switch and wait_until > next_switch):
                wait_until = next_switch

            if wait_until and wait_until < end_time:
                self.set_time(wait_until)
                self.machine_run()
            else:
                break

        self.set_time(end_time)
        self.machine_run()

    def machine_run(self):
        self.machine.log.debug("Next run %s", time.time())
        self.machine.default_platform.tick()
        self.machine.timer_tick()

    def unittest_verbosity(self):
        """Return the verbosity setting of the currently running unittest
        program, or 0 if none is running.

        """
        frame = inspect.currentframe()
        while frame:
            self = frame.f_locals.get('self')
            if isinstance(self, unittest.TestProgram):
                return self.verbosity
            frame = frame.f_back
        return 0

    def setUp(self):
        if self.unittest_verbosity() > 1:
                logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s : %(levelname)s : %(name)s : %(message)s')
        else:
                # no logging by default
                logging.basicConfig(level=99)

        self.realTime = time.time
        self.testTime = self.realTime()
        time.time = MagicMock(return_value=self.testTime)

        # init machine
        self.machine = TestMachineController(self.getOptions(),
                                             self.machine_config_patches)

        self.machine.default_platform.timer_initialize()
        self.machine.loop_start_time = time.time()

        self.machine.ball_controller.num_balls_known = 99
        self.advance_time_and_run(300)

    def tearDown(self):
        if sys.exc_info != (None, None, None):
            # disable teardown logging after error
            logging.basicConfig(level=99)
        # fire all delays
        self.advance_time_and_run(300)
        self.machine = None
        time.time = self.realTime
        self.realTime = None
