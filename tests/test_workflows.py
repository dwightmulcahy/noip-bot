import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class WorkflowTests(unittest.TestCase):
    def test_ci_verifies_pushes_and_pull_requests(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("docker/build-push-action@v6", workflow)

    def test_release_publishes_multi_arch_docker_hub_image(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn("types:\n      - published", workflow)
        self.assertIn("IMAGE_NAME: dwightmulcahy/noip-bot", workflow)
        self.assertIn("platforms: linux/amd64,linux/arm64", workflow)
        self.assertIn("push: true", workflow)
        self.assertIn("secrets.DOCKERHUB_USERNAME", workflow)
        self.assertIn("secrets.DOCKERHUB_TOKEN", workflow)


if __name__ == "__main__":
    unittest.main()
