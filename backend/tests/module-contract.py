"""Check the Frappe module-to-controller contract without a running site."""
import ast
import json
from pathlib import Path
import unittest

APP = Path(__file__).resolve().parents[1] / "apps/rayher_crm/rayher_crm"

def module_package(module):
    return module.lower().replace(" ", "_").replace("-", "_")

class ModuleContract(unittest.TestCase):
    def setUp(self):
        self.modules = [line.strip() for line in (APP / "modules.txt").read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_registered_modules_resolve_to_controller_packages(self):
        self.assertTrue(self.modules)
        for module in self.modules:
            with self.subTest(module=module):
                self.assertTrue((APP / module_package(module) / "doctype/__init__.py").is_file(), "Registered module has no controller package")

    def test_doctype_modules_resolve_to_their_controller_directory(self):
        definitions = list(APP.glob("*/doctype/*/*.json"))
        self.assertTrue(definitions)
        for path in definitions:
            definition = json.loads(path.read_text(encoding="utf-8"))
            if definition.get("doctype") != "DocType":
                continue
            with self.subTest(doctype=definition["name"]):
                self.assertIn(definition["module"], self.modules)
                self.assertEqual(module_package(definition["module"]), path.parents[2].name)

    def test_permission_registry_targets_the_registered_module(self):
        tree = ast.parse((APP / "permissions/registry.py").read_text(encoding="utf-8"))
        module = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "APP_MODULE" for target in node.targets))
        self.assertEqual(self.modules, [module])

if __name__ == "__main__":
    unittest.main()
