"""Unit checks for main-thread guards, using a minimal Autodesk stub."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class GuardTests(unittest.TestCase):
    def setUp(self):
        core=types.ModuleType('adsk.core');core.CustomEventHandler=object
        fusion=types.ModuleType('adsk.fusion')
        adsk=types.ModuleType('adsk');adsk.core=core;adsk.fusion=fusion
        path=Path(__file__).parents[1]/'addin'/'FusionBridge'/'FusionBridge.py'
        with patch.dict(sys.modules,{'adsk':adsk,'adsk.core':core,'adsk.fusion':fusion}):
            spec=importlib.util.spec_from_file_location('bridge_guard_test',path)
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.module.app=types.SimpleNamespace(userInterface=types.SimpleNamespace(activeCommand='SelectCommand'))
        self.temp=tempfile.TemporaryDirectory();self.module.STATE=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def test_busy_command_refused_before_document_access(self):
        self.module.app.userInterface.activeCommand='ExtrudeCommand'
        with self.assertRaisesRegex(RuntimeError,'busy'):
            self.module.dispatch('set_parameter',{})

    def test_wrong_document_refused(self):
        self.module.app.activeDocument=types.SimpleNamespace(isValid=True)
        with self.assertRaisesRegex(ValueError,'Document mismatch'):
            self.module.active_design({'document_id':'not-the-current-document'})

    def test_document_id_stable_within_session(self):
        doc=types.SimpleNamespace(isValid=True)
        self.assertEqual(self.module.doc_id(doc),self.module.doc_id(doc))

    def test_python_requires_ack_before_backup(self):
        self.module.active_design=Mock(return_value=(object(),types.SimpleNamespace(rootComponent=object())))
        self.module.backup=Mock()
        with self.assertRaisesRegex(ValueError,'NOT sandboxed'):
            self.module.dispatch('execute_python',{'code':'result=1'})
        self.module.backup.assert_not_called()

    def test_python_syntax_checked_before_backup(self):
        self.module.active_design=Mock(return_value=(object(),types.SimpleNamespace(rootComponent=object())))
        self.module.backup=Mock()
        with self.assertRaises(SyntaxError):
            self.module.dispatch('execute_python',{'code':'def invalid','acknowledge_full_access':True})
        self.module.backup.assert_not_called()

    def test_backup_failure_refuses_edit(self):
        manager=Mock();manager.execute.return_value=False
        with self.assertRaisesRegex(RuntimeError,'edit refused'):
            self.module.backup(types.SimpleNamespace(exportManager=manager))

    def test_export_path_cannot_escape_artifact_directory(self):
        for name in ('../data.f3d','C:\\data.f3d','nested/data.f3d','bad:stream.f3d'):
            with self.assertRaises(ValueError):self.module.artifact(name,'.f3d')

    def test_exports_do_not_overwrite(self):
        first=self.module.artifact('model.f3d','.f3d')
        second=self.module.artifact('model.f3d','.f3d')
        self.assertNotEqual(first,second)


if __name__=='__main__':unittest.main()
