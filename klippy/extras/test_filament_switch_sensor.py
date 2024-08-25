from unittest import TestCase
from unittest.mock import Mock

from extras.filament_switch_sensor import RunoutHelper

class TestRunoutHelper(TestCase):
    # Constants
    NOW = 0.
    NEVER = 9999999999999999.

    # Config
    pause_on_runout = True
    pause_delay = .5
    event_delay = 3.
    debounce_delay = 0.1

    # Current time
    eventtime = 0

    # State
    printing = False

    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        self.run_in_template = Mock()
        self.run_in_template.render.return_value = ''
        self.run_out_template = Mock()
        self.run_out_template.render.return_value = ''
        self.config = Mock()
        self.config.get_name.return_value = 'My Test Config'
        self.config.getboolean.side_effect = self.getboolean
        self.config.getfloat.side_effect = self.getfloat
        printer = self.config.get_printer()
        lookup_object = printer.lookup_object()
        lookup_object.get_status.side_effect = self.get_status
        printer.load_object().load_template.side_effect = self.load_template
        self.reactor = printer.get_reactor()
        self.reactor.NEVER = self.NEVER
        self.reactor.monotonic.side_effect = self.monotonic
        self.update_timer = self.reactor.update_timer
        self.register_callback = self.reactor.register_callback

    def getboolean(self, section: str, option: str):
        if section == 'pause_on_runout':
            return self.pause_on_runout
        return option

    def getfloat(self, option, default=None, minval=None, maxval=None,
        above=None, below=None, note_valid=True):
        if option == 'pause_delay':
            return self.pause_delay
        elif option == 'event_delay':
            return self.event_delay
        elif option == 'debounce_delay':
            return self.debounce_delay
        return default

    def load_template(self, *args, ** kwargs):
        option = args[1]
        if option == 'insert_gcode':
            return self.run_in_template
        elif option == 'runout_gcode':
            return self.run_out_template
        return None

    def monotonic(self):
        return self.eventtime

    def get_status(self, eventtime):
        return { 'state' : 'Printing' if self.printing else '' }

    def reset_mock(self):
        self.config.reset_mock()


    ### TESTS ###

    def test_init(self) -> RunoutHelper:
        self.eventtime = 0
        helper = RunoutHelper(self.config)
        self.reactor.register_timer.assert_called_once_with(helper.debounce_filament_present, self.NEVER)
        self.assertEqual(helper.min_event_systime, self.NEVER)
        helper._handle_ready()
        self.assertEqual(helper.min_event_systime, self.eventtime + self.debounce_delay + 2)
        return helper


    #### NO DEBOUNCE TESTS ####

    def test_note_filament_present_in_before_ready(self):
        self.debounce_delay = 0.
        helper = self.test_init()

        self.eventtime = 1
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()
        self.register_callback.assert_not_called()
        
    def test_note_filament_present_in_no_printing(self):
        self.debounce_delay = 0.
        helper = self.test_init()

        # Filament in
        self.printing = False
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()
        self.register_callback.assert_called_once_with(helper._insert_event_handler)
        helper._insert_event_handler(self.eventtime)

    def test_note_filament_present_in_printing(self):
        self.debounce_delay = 0.
        helper = self.test_init()

        # Filament in
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()
        self.register_callback.assert_not_called()

    def test_note_filament_present_out_printing(self):
        self.debounce_delay = 0.
        helper = self.test_init()

        # Filament out
        helper.filament_present = True
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()
        self.register_callback.assert_called_once_with(helper._runout_event_handler)
        helper._runout_event_handler(self.eventtime)

    def test_note_filament_present_out_no_printing(self):
        self.debounce_delay = 0.
        helper = self.test_init()

        # Filament out
        helper.filament_present = True
        self.printing = False
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()
        self.register_callback.assert_not_called()


    #### DEBOUNCE TESTS ####

    def test_note_filament_present_debounce_in_before_ready(self):
        helper = self.test_init()

        self.eventtime = 1
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, True)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler,
                                                          self.eventtime + self.debounce_delay)

        self.eventtime += self.debounce_delay
        self.reset_mock()
        self.assertEqual(helper.debounce_filament_present(), self.NEVER)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.register_callback.assert_not_called()

    def test_note_filament_present_debounce_in(self):
        helper = self.test_init()

        # Filament in
        self.printing = False
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, True)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler,
                                                          self.eventtime + self.debounce_delay)

        self.eventtime += self.debounce_delay
        self.reset_mock()
        self.assertEqual(helper.debounce_filament_present(), self.NEVER)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.register_callback.assert_called_once_with(helper._insert_event_handler)
        helper._insert_event_handler(self.eventtime)

    def test_note_filament_present_debounce_out(self):
        helper = self.test_init()

        helper.filament_present = True
        # Filament out
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, False)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler, self.eventtime + self.debounce_delay)

        self.eventtime += self.debounce_delay
        self.reset_mock()
        self.assertEqual(helper.debounce_filament_present(), self.NEVER)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, None)
        self.register_callback.assert_called_once_with(helper._runout_event_handler)
        helper._runout_event_handler(self.eventtime)

    def test_note_filament_present_debounce_in_cancel(self):
        helper = self.test_init()

        helper.filament_present = False

        # Filament in
        self.printing = False
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, True)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler,
                                                     self.eventtime + self.debounce_delay)

        # Filament out
        self.printing = False
        self.eventtime += self.debounce_delay / 2.
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler, self.NEVER)

    def test_note_filament_present_debounce_out_cancel(self):
        helper = self.test_init()

        helper.filament_present = True

        # Filament out
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, False)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler,
                                                     self.eventtime + self.debounce_delay)

        # Filament in
        self.printing = True
        self.eventtime += self.debounce_delay / 2.
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler, self.NEVER)

    def test_note_filament_present_debounce_in_no_change(self):
        helper = self.test_init()

        helper.filament_present = True

        # Filament in
        self.printing = False
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()

    def test_note_filament_present_debounce_out_no_change(self):
        helper = self.test_init()

        helper.filament_present = False

        # Filament out
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, None)
        self.update_timer.assert_not_called()

    def test_note_filament_present_debounce_in_duplicate(self):
        helper = self.test_init()

        helper.filament_present = False

        # Filament in
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, True)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler,  self.eventtime + self.debounce_delay)

        # Duplicate filament in
        self.printing = True
        self.eventtime += self.debounce_delay / 2.
        self.reset_mock()
        helper.note_filament_present(True)
        self.assertEqual(helper.filament_present, False)
        self.assertEqual(helper.filament_present_next, True)
        self.update_timer.assert_not_called()

    def test_note_filament_present_debounce_out_duplicate(self):
        helper = self.test_init()

        helper.filament_present = True

        # Filament out
        self.printing = True
        self.eventtime = 3
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, False)
        self.update_timer.assert_called_once_with(helper.debounce_filament_present_handler,
                                                  self.eventtime + self.debounce_delay)

        # Duplicate filament out
        self.printing = True
        self.eventtime = self.debounce_delay / 2.
        self.reset_mock()
        helper.note_filament_present(False)
        self.assertEqual(helper.filament_present, True)
        self.assertEqual(helper.filament_present_next, False)
        self.update_timer.assert_not_called()
