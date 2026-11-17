import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, call

spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).parent / 'wrapper/manage.py')
lifecycle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lifecycle)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name)
        self.old = self.state / 'releases/old'
        self.new = self.state / 'releases/new'
        self.old.mkdir(parents=True)
        self.new.mkdir()

    def test_first_apply_and_repeat_do_not_create_false_rollback(self):
        with patch.object(lifecycle, 'compose') as compose, patch.object(lifecycle, 'wait_healthy'):
            lifecycle.apply_release(self.state, self.new)
            lifecycle.apply_release(self.state, self.new)
        self.assertEqual(lifecycle.pointer(self.state, 'current'), self.new)
        self.assertIsNone(lifecycle.pointer(self.state, 'previous'))
        self.assertEqual(compose.call_args, call(self.new, 'up', '-d', '--no-build', '--pull', 'never', 'music-wrapper'))

    def test_update_retains_previous_release(self):
        lifecycle.set_pointer(self.state, 'current', self.old)
        with patch.object(lifecycle, 'compose'), patch.object(lifecycle, 'wait_healthy'):
            lifecycle.apply_release(self.state, self.new)
        self.assertEqual(lifecycle.pointer(self.state, 'current'), self.new)
        self.assertEqual(lifecycle.pointer(self.state, 'previous'), self.old)

    def test_failed_update_restores_old_without_changing_pointers(self):
        lifecycle.set_pointer(self.state, 'current', self.old)
        with patch.object(lifecycle, 'compose') as compose, patch.object(lifecycle, 'wait_healthy', side_effect=[RuntimeError('unhealthy'), None]):
            with self.assertRaisesRegex(RuntimeError, 'unhealthy'):
                lifecycle.apply_release(self.state, self.new)
        self.assertEqual(compose.call_args_list, [
            call(self.new, 'up', '-d', '--no-build', '--pull', 'never', 'music-wrapper'),
            call(self.old, 'up', '-d', '--no-build', '--pull', 'never', 'music-wrapper')])
        self.assertEqual(lifecycle.pointer(self.state, 'current'), self.old)

    def test_first_failed_release_is_stopped(self):
        with patch.object(lifecycle, 'compose') as compose, patch.object(lifecycle, 'wait_healthy', side_effect=RuntimeError('unhealthy')):
            with self.assertRaises(RuntimeError):
                lifecycle.apply_release(self.state, self.new)
        self.assertEqual(compose.call_args, call(self.new, 'stop', 'music-wrapper'))
        self.assertIsNone(lifecycle.pointer(self.state, 'current'))

    def test_rollback_retains_release_to_roll_forward(self):
        lifecycle.set_pointer(self.state, 'current', self.new)
        lifecycle.set_pointer(self.state, 'previous', self.old)
        with patch.object(lifecycle, 'compose'), patch.object(lifecycle, 'wait_healthy'):
            lifecycle.apply_release(self.state, lifecycle.pointer(self.state, 'previous'))
        self.assertEqual(lifecycle.pointer(self.state, 'current'), self.old)
        self.assertEqual(lifecycle.pointer(self.state, 'previous'), self.new)

    def test_compose_always_targets_companion_project(self):
        with patch.object(lifecycle, 'run') as run:
            lifecycle.compose(self.new, 'stop', 'music-wrapper')
        self.assertEqual(run.call_args, call('docker', 'compose', '--project-name', 'music-wrapper',
            '--env-file', str(self.new / 'compose.env'), '-f', str(self.new / 'compose.yaml'), 'stop', 'music-wrapper'))

    def test_external_release_pointer_is_rejected(self):
        (self.state / 'current').symlink_to('/tmp')
        with self.assertRaises(RuntimeError):
            lifecycle.pointer(self.state, 'current')
