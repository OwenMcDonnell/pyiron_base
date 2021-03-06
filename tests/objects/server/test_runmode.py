import unittest
from pyiron_base.objects.server.runmode import Runmode


class TestRunmode(unittest.TestCase):
    def setUp(self):
        self.run_mode_default = Runmode()
        self.run_mode_modal = Runmode()
        self.run_mode_modal.mode = 'modal'
        self.run_mode_non_modal = Runmode()
        self.run_mode_non_modal.mode = 'non_modal'
        self.run_mode_queue = Runmode()
        self.run_mode_queue.mode = 'queue'
        self.run_mode_manual = Runmode()
        self.run_mode_manual.mode = 'manual'

    def test_modal(self):
        self.assertTrue(self.run_mode_default.modal)
        self.assertTrue(self.run_mode_modal.modal)
        self.assertFalse(self.run_mode_non_modal.modal)
        self.assertFalse(self.run_mode_queue.modal)
        self.assertFalse(self.run_mode_manual.modal)

    def test_non_modal(self):
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_modal.non_modal)
        self.assertTrue(self.run_mode_non_modal.non_modal)
        self.assertFalse(self.run_mode_queue.non_modal)
        self.assertFalse(self.run_mode_manual.non_modal)

    def test_queue(self):
        self.assertFalse(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_modal.queue)
        self.assertFalse(self.run_mode_non_modal.queue)
        self.assertTrue(self.run_mode_queue.queue)
        self.assertFalse(self.run_mode_manual.queue)

    def test_manual(self):
        self.assertFalse(self.run_mode_default.manual)
        self.assertFalse(self.run_mode_modal.manual)
        self.assertFalse(self.run_mode_non_modal.manual)
        self.assertFalse(self.run_mode_queue.manual)
        self.assertTrue(self.run_mode_manual.manual)

    def test_mode(self):
        self.run_mode_default.mode = 'non_modal'
        self.assertFalse(self.run_mode_default.modal)
        self.assertTrue(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_default.manual)
        self.run_mode_default.mode = 'queue'
        self.assertFalse(self.run_mode_default.modal)
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertTrue(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_default.manual)
        self.run_mode_default.mode = 'manual'
        self.assertFalse(self.run_mode_default.modal)
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_default.queue)
        self.assertTrue(self.run_mode_default.manual)
        self.run_mode_default.mode = 'modal'
        self.assertTrue(self.run_mode_default.modal)
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_default.manual)

    def test_setter(self):
        self.run_mode_default.non_modal = True
        self.assertFalse(self.run_mode_default.modal)
        self.assertTrue(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_default.manual)
        self.run_mode_default.queue = True
        self.assertFalse(self.run_mode_default.modal)
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertTrue(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_default.manual)
        self.run_mode_default.manual = True
        self.assertFalse(self.run_mode_default.modal)
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_default.queue)
        self.assertTrue(self.run_mode_default.manual)
        self.run_mode_default.modal = True
        self.assertTrue(self.run_mode_default.modal)
        self.assertFalse(self.run_mode_default.non_modal)
        self.assertFalse(self.run_mode_default.queue)
        self.assertFalse(self.run_mode_default.manual)


if __name__ == '__main__':
    unittest.main()