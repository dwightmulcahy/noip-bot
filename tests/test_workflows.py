import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class WorkflowTests(unittest.TestCase):
    def test_ci_verifies_pushes_and_pull_requests(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("ruff check .", workflow)
        self.assertIn("ruff format --check .", workflow)
        self.assertIn("run: mypy", workflow)
        self.assertRegex(workflow, r"docker/build-push-action@[0-9a-f]{40}")
        self.assertIn("scripts/container_smoke_test.sh", workflow)
        self.assertIn("aquasecurity/trivy-action@", workflow)
        self.assertIn("severity: CRITICAL,HIGH", workflow)

    def test_release_publishes_multi_arch_docker_hub_image(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn('tags:\n      - "*.*.*"', workflow)
        self.assertIn("github.ref_name", workflow)
        self.assertIn("refs/heads/release:refs/remotes/origin/release", workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("IMAGE_NAME: dwightmulcahy/noip-bot", workflow)
        self.assertIn("platforms: linux/amd64,linux/arm64", workflow)
        self.assertIn("APP_VERSION=${{ env.RELEASE_TAG }}", workflow)
        self.assertIn("push: true", workflow)
        self.assertIn("secrets.DOCKERHUB_USERNAME", workflow)
        self.assertIn("secrets.DOCKERHUB_TOKEN", workflow)
        self.assertIn("type=semver,pattern={{version}}", workflow)
        self.assertIn("group: docker-release", workflow)
        self.assertNotIn("group: docker-release-${{ github.ref_name }}", workflow)
        self.assertIn("id: release_version", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn(
            "type=semver,pattern={{major}},enable=${{ "
            "needs.preflight.outputs.is_latest == 'true' }}",
            workflow,
        )
        self.assertIn(
            "type=raw,value=latest,enable=${{ "
            "needs.preflight.outputs.is_latest == 'true' }}",
            workflow,
        )
        self.assertIn("needs: preflight", workflow)
        self.assertIn("provenance: mode=max", workflow)
        self.assertIn("sbom: true", workflow)

    def test_all_external_actions_are_pinned_to_full_shas(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text()
            references = re.findall(r"uses:\s+([^\s#]+)", workflow)
            for reference in references:
                with self.subTest(workflow=path.name, reference=reference):
                    self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")

    def test_dependabot_covers_supported_ecosystems(self):
        config = (ROOT / ".github" / "dependabot.yml").read_text()
        self.assertIn("package-ecosystem: pip", config)
        self.assertIn("package-ecosystem: docker", config)
        self.assertIn("package-ecosystem: github-actions", config)


if __name__ == "__main__":
    unittest.main()
