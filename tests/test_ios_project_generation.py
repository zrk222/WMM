"""Validate generated build inputs; Apple parser/build acceptance remains separate."""
import json
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[1]


class NativeProjectGenerationTests(unittest.TestCase):
    def test_test_plan_references_resolve_and_configuration_ids_are_uuids(self):
        with tempfile.TemporaryDirectory() as folder:
            ios=Path(folder)/'ios';build=ios/'Build';build.mkdir(parents=True)
            script=build/'generate_project.py'
            shutil.copyfile(ROOT/'ios/Build/generate_project.py',script)
            subprocess.run([sys.executable,str(script)],check=True,capture_output=True)
            project=ios/'WMM.xcodeproj'
            scheme=ElementTree.parse(project/'xcshareddata/xcschemes/WMM.xcscheme')
            refs=scheme.findall('.//TestPlanReference')
            self.assertEqual(len(refs),2)
            target_ids=set()
            for ref in refs:
                relative=ref.attrib['reference'].removeprefix('container:')
                plan=json.loads((ios/relative).read_text(encoding='utf-8'))
                self.assertEqual(plan['version'],1)
                for config in plan['configurations']:
                    self.assertEqual(str(uuid.UUID(config['id'])),config['id'])
                self.assertTrue(plan['testTargets'])
                target=plan['testTargets'][0]['target']
                self.assertEqual(target['name'],'WMMTests')
                target_ids.add(target['identifier'])
            self.assertEqual(len(target_ids),1)
            text=(project/'project.pbxproj').read_text(encoding='utf-8')
            self.assertIn('"WMMTests/EngineBootstrapTests.swift"',text)
            self.assertIn('"WMMTests/BridgeAgentTests.swift"',text)
            self.assertIn('"WMM/Bridge/DomainBridge.swift"',text)
            self.assertIn('"WMM/Agents/ScopedAgentRuntime.swift"',text)
            self.assertIn('"WMM/Agents/NativeAgentAccessView.swift"',text)
            self.assertIn('"WMM/Jobs/LocalScheduler.swift"',text)
            self.assertIn('"WMM/Jobs/NativeJobsView.swift"',text)
            self.assertIn('"WMM/Identity/NativeSessionAuthority.swift"',text)
            self.assertIn('"WMM/Workflow/WorkflowNavigation.swift"',text)
            self.assertIn('"WMM/Workflow/NativeWorkspaceModel.swift"',text)
            self.assertIn('"WMM/Reports/NativeResultsView.swift"',text)
            self.assertIn('"WMM/Media/NativeMediaLibrary.swift"',text)
            self.assertIn('"WMM/Media/NativeEditorModel.swift"',text)
            self.assertIn('"WMM/Media/NativeEditorView.swift"',text)
            self.assertIn('"INFOPLIST_KEY_NSFaceIDUsageDescription"',text)
            self.assertIn('"CODE_SIGN_ENTITLEMENTS[sdk=iphonesimulator*]"',text)
            self.assertNotIn('"CODE_SIGN_ENTITLEMENTS" =',text)
            entitlements=plistlib.loads((ROOT/'ios/WMM/Simulator.entitlements').read_bytes())
            self.assertEqual(entitlements['keychain-access-groups'],[entitlements['application-identifier']])
            self.assertIn('"WMMTests/MediaConformanceTests.swift"',text)
            for target_id in target_ids:self.assertIn('"'+target_id+'"',text)
            initial={p.relative_to(project).as_posix():p.read_bytes() for p in project.rglob('*') if p.is_file()}
            subprocess.run([sys.executable,str(script)],check=True,capture_output=True)
            self.assertEqual(initial,{p.relative_to(project).as_posix():p.read_bytes() for p in project.rglob('*') if p.is_file()})
