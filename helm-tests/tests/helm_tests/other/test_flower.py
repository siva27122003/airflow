# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import jmespath
import pytest
from chart_utils.helm_template_generator import render_chart


class TestFlowerDeployment:
    """Tests flower deployment."""

    @pytest.mark.parametrize(
        "executor,flower_enabled,created",
        [
            ("CeleryExecutor", False, False),
            ("CeleryKubernetesExecutor", False, False),
            ("CeleryExecutor,KubernetesExecutor", False, False),
            ("KubernetesExecutor", False, False),
            ("CeleryExecutor", True, True),
            ("CeleryKubernetesExecutor", True, True),
            ("CeleryExecutor,KubernetesExecutor", True, True),
            ("KubernetesExecutor", True, False),
        ],
    )
    def test_create_flower(self, executor, flower_enabled, created):
        docs = render_chart(
            values={"executor": executor, "flower": {"enabled": flower_enabled}},
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert bool(docs) is created
        if created:
            assert jmespath.search("metadata.name", docs[0]) == "release-name-flower"
            assert jmespath.search("spec.template.spec.containers[0].name", docs[0]) == "flower"

    @pytest.mark.parametrize(
        "revision_history_limit, global_revision_history_limit",
        [(8, 10), (10, 8), (8, None), (None, 10), (None, None)],
    )
    def test_revision_history_limit(self, revision_history_limit, global_revision_history_limit):
        values = {
            "flower": {
                "enabled": True,
            }
        }
        if revision_history_limit:
            values["flower"]["revisionHistoryLimit"] = revision_history_limit
        if global_revision_history_limit:
            values["revisionHistoryLimit"] = global_revision_history_limit
        docs = render_chart(
            values=values,
            show_only=["templates/flower/flower-deployment.yaml"],
        )
        expected_result = revision_history_limit or global_revision_history_limit
        assert jmespath.search("spec.revisionHistoryLimit", docs[0]) == expected_result

    @pytest.mark.parametrize(
        "airflow_version, expected_arg",
        [
            ("2.0.2", "airflow celery flower"),
            ("1.10.14", "airflow flower"),
            ("1.9.0", "airflow flower"),
            ("2.1.0", "airflow celery flower"),
        ],
    )
    def test_args_with_airflow_version(self, airflow_version, expected_arg):
        docs = render_chart(
            values={
                "executor": "CeleryExecutor",
                "flower": {"enabled": True},
                "airflowVersion": airflow_version,
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert jmespath.search("spec.template.spec.containers[0].args", docs[0]) == [
            "bash",
            "-c",
            f"exec \\\n{expected_arg}",
        ]

    @pytest.mark.parametrize(
        "command, args",
        [
            (None, None),
            (None, ["custom", "args"]),
            (["custom", "command"], None),
            (["custom", "command"], ["custom", "args"]),
        ],
    )
    def test_command_and_args_overrides(self, command, args):
        docs = render_chart(
            values={"flower": {"enabled": True, "command": command, "args": args}},
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert command == jmespath.search("spec.template.spec.containers[0].command", docs[0])
        assert args == jmespath.search("spec.template.spec.containers[0].args", docs[0])

    def test_command_and_args_overrides_are_templated(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "command": ["{{ .Release.Name }}"],
                    "args": ["{{ .Release.Service }}"],
                }
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert jmespath.search("spec.template.spec.containers[0].command", docs[0]) == ["release-name"]
        assert jmespath.search("spec.template.spec.containers[0].args", docs[0]) == ["Helm"]

    def test_should_create_flower_deployment_with_authorization(self):
        docs = render_chart(
            values={
                "flower": {"enabled": True, "username": "flower", "password": "fl0w3r"},
                "ports": {"flowerUI": 7777},
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert (
            jmespath.search("spec.template.spec.containers[0].env[0].name", docs[0])
            == "AIRFLOW__CELERY__FLOWER_BASIC_AUTH"
        )
        assert jmespath.search("spec.template.spec.containers[0].livenessProbe.exec.command", docs[0]) == [
            "curl",
            "--user",
            "$AIRFLOW__CELERY__FLOWER_BASIC_AUTH",
            "localhost:7777",
        ]
        assert jmespath.search("spec.template.spec.containers[0].readinessProbe.exec.command", docs[0]) == [
            "curl",
            "--user",
            "$AIRFLOW__CELERY__FLOWER_BASIC_AUTH",
            "localhost:7777",
        ]
        assert jmespath.search("spec.template.spec.containers[0].startupProbe.exec.command", docs[0]) == [
            "curl",
            "--user",
            "$AIRFLOW__CELERY__FLOWER_BASIC_AUTH",
            "localhost:7777",
        ]

    def test_should_create_flower_deployment_without_authorization(self):
        docs = render_chart(
            values={
                "flower": {"enabled": True},
                "ports": {"flowerUI": 7777},
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert (
            jmespath.search("spec.template.spec.containers[0].env[0].name", docs[0])
            == "AIRFLOW__CORE__FERNET_KEY"
        )
        assert jmespath.search("spec.template.spec.containers[0].livenessProbe.exec.command", docs[0]) == [
            "curl",
            "localhost:7777",
        ]
        assert jmespath.search("spec.template.spec.containers[0].readinessProbe.exec.command", docs[0]) == [
            "curl",
            "localhost:7777",
        ]
        assert jmespath.search("spec.template.spec.containers[0].startupProbe.exec.command", docs[0]) == [
            "curl",
            "localhost:7777",
        ]

    def test_scheduler_name(self):
        docs = render_chart(
            values={"flower": {"enabled": True}, "schedulerName": "airflow-scheduler"},
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert (
            jmespath.search(
                "spec.template.spec.schedulerName",
                docs[0],
            )
            == "airflow-scheduler"
        )

    def test_should_create_valid_affinity_tolerations_and_node_selector(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "affinity": {
                        "nodeAffinity": {
                            "requiredDuringSchedulingIgnoredDuringExecution": {
                                "nodeSelectorTerms": [
                                    {
                                        "matchExpressions": [
                                            {"key": "foo", "operator": "In", "values": ["true"]},
                                        ]
                                    }
                                ]
                            }
                        }
                    },
                    "tolerations": [
                        {"key": "dynamic-pods", "operator": "Equal", "value": "true", "effect": "NoSchedule"}
                    ],
                    "nodeSelector": {"diskType": "ssd"},
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert jmespath.search("kind", docs[0]) == "Deployment"
        assert (
            jmespath.search(
                "spec.template.spec.affinity.nodeAffinity."
                "requiredDuringSchedulingIgnoredDuringExecution."
                "nodeSelectorTerms[0]."
                "matchExpressions[0]."
                "key",
                docs[0],
            )
            == "foo"
        )
        assert (
            jmespath.search(
                "spec.template.spec.nodeSelector.diskType",
                docs[0],
            )
            == "ssd"
        )
        assert (
            jmespath.search(
                "spec.template.spec.tolerations[0].key",
                docs[0],
            )
            == "dynamic-pods"
        )

    def test_flower_resources_are_configurable(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "resources": {
                        "limits": {"cpu": "200m", "memory": "128Mi"},
                        "requests": {"cpu": "300m", "memory": "169Mi"},
                    },
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )
        assert jmespath.search("spec.template.spec.containers[0].resources.limits.memory", docs[0]) == "128Mi"
        assert (
            jmespath.search("spec.template.spec.containers[0].resources.requests.memory", docs[0]) == "169Mi"
        )
        assert jmespath.search("spec.template.spec.containers[0].resources.requests.cpu", docs[0]) == "300m"

    def test_flower_resources_are_not_added_by_default(self):
        docs = render_chart(
            values={"flower": {"enabled": True}},
            show_only=["templates/flower/flower-deployment.yaml"],
        )
        assert jmespath.search("spec.template.spec.containers[0].resources", docs[0]) == {}

    def test_should_add_extra_containers(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "extraContainers": [
                        {"name": "{{ .Chart.Name }}", "image": "test-registry/test-repo:test-tag"}
                    ],
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert jmespath.search("spec.template.spec.containers[-1]", docs[0]) == {
            "name": "airflow",
            "image": "test-registry/test-repo:test-tag",
        }

    def test_should_add_extra_volume_and_extra_volume_mount(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "extraVolumes": [{"name": "myvolume-{{ .Chart.Name }}", "emptyDir": {}}],
                    "extraVolumeMounts": [{"name": "myvolume-{{ .Chart.Name }}", "mountPath": "/opt/test"}],
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert {"name": "myvolume-airflow", "emptyDir": {}} in jmespath.search(
            "spec.template.spec.volumes", docs[0]
        )
        assert {"name": "myvolume-airflow", "mountPath": "/opt/test"} in jmespath.search(
            "spec.template.spec.containers[0].volumeMounts", docs[0]
        )

    def test_should_add_global_volume_and_global_volume_mount(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                },
                "volumes": [{"name": "myvolume", "emptyDir": {}}],
                "volumeMounts": [{"name": "myvolume", "mountPath": "/opt/test"}],
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert {"name": "myvolume", "emptyDir": {}} in jmespath.search("spec.template.spec.volumes", docs[0])
        assert {"name": "myvolume", "mountPath": "/opt/test"} in jmespath.search(
            "spec.template.spec.containers[0].volumeMounts", docs[0]
        )

    def test_should_add_extraEnvs(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "env": [
                        {"name": "TEST_ENV_1", "value": "test_env_1"},
                        {
                            "name": "TEST_ENV_2",
                            "valueFrom": {"secretKeyRef": {"name": "my-secret", "key": "my-key"}},
                        },
                        {
                            "name": "TEST_ENV_3",
                            "valueFrom": {"configMapKeyRef": {"name": "my-config-map", "key": "my-key"}},
                        },
                    ],
                }
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert {"name": "TEST_ENV_1", "value": "test_env_1"} in jmespath.search(
            "spec.template.spec.containers[0].env", docs[0]
        )
        assert {
            "name": "TEST_ENV_2",
            "valueFrom": {"secretKeyRef": {"name": "my-secret", "key": "my-key"}},
        } in jmespath.search("spec.template.spec.containers[0].env", docs[0])
        assert {
            "name": "TEST_ENV_3",
            "valueFrom": {"configMapKeyRef": {"name": "my-config-map", "key": "my-key"}},
        } in jmespath.search("spec.template.spec.containers[0].env", docs[0])

    def test_should_add_component_specific_labels(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "labels": {"test_label": "test_label_value"},
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert "test_label" in jmespath.search("spec.template.metadata.labels", docs[0])
        assert jmespath.search("spec.template.metadata.labels", docs[0])["test_label"] == "test_label_value"

    def test_no_airflow_local_settings(self):
        docs = render_chart(
            values={"flower": {"enabled": True}, "airflowLocalSettings": None},
            show_only=["templates/flower/flower-deployment.yaml"],
        )
        volume_mounts = jmespath.search("spec.template.spec.containers[0].volumeMounts", docs[0])
        assert "airflow_local_settings.py" not in str(volume_mounts)

    def test_airflow_local_settings(self):
        docs = render_chart(
            values={"flower": {"enabled": True}, "airflowLocalSettings": "# Well hello!"},
            show_only=["templates/flower/flower-deployment.yaml"],
        )
        volume_mount = {
            "name": "config",
            "mountPath": "/opt/airflow/config/airflow_local_settings.py",
            "subPath": "airflow_local_settings.py",
            "readOnly": True,
        }
        assert volume_mount in jmespath.search("spec.template.spec.containers[0].volumeMounts", docs[0])

    def test_should_add_component_specific_annotations(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "annotations": {"test_annotation": "test_annotation_value"},
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )
        assert "annotations" in jmespath.search("metadata", docs[0])
        assert jmespath.search("metadata.annotations", docs[0])["test_annotation"] == "test_annotation_value"

    @pytest.mark.parametrize("probe", ["livenessProbe", "readinessProbe"])
    def test_probe_values_are_configurable(self, probe):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    probe: {
                        "initialDelaySeconds": 111,
                        "timeoutSeconds": 222,
                        "failureThreshold": 333,
                        "periodSeconds": 444,
                    },
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert (
            jmespath.search(f"spec.template.spec.containers[0].{probe}.initialDelaySeconds", docs[0]) == 111
        )
        assert jmespath.search(f"spec.template.spec.containers[0].{probe}.timeoutSeconds", docs[0]) == 222
        assert jmespath.search(f"spec.template.spec.containers[0].{probe}.failureThreshold", docs[0]) == 333
        assert jmespath.search(f"spec.template.spec.containers[0].{probe}.periodSeconds", docs[0]) == 444

    def test_startup_probe_values_are_configurable(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "startupProbe": {
                        "timeoutSeconds": 222,
                        "failureThreshold": 333,
                        "periodSeconds": 444,
                    },
                },
            },
            show_only=["templates/flower/flower-deployment.yaml"],
        )

        assert jmespath.search("spec.template.spec.containers[0].startupProbe.timeoutSeconds", docs[0]) == 222
        assert (
            jmespath.search("spec.template.spec.containers[0].startupProbe.failureThreshold", docs[0]) == 333
        )
        assert jmespath.search("spec.template.spec.containers[0].startupProbe.periodSeconds", docs[0]) == 444


class TestFlowerService:
    """Tests flower service."""

    @pytest.mark.parametrize(
        "executor,flower_enabled,created",
        [
            ("CeleryExecutor", False, False),
            ("CeleryKubernetesExecutor", False, False),
            ("KubernetesExecutor", False, False),
            ("CeleryExecutor", True, True),
            ("CeleryKubernetesExecutor", True, True),
            ("KubernetesExecutor", True, False),
        ],
    )
    def test_create_flower(self, executor, flower_enabled, created):
        docs = render_chart(
            values={"executor": executor, "flower": {"enabled": flower_enabled}},
            show_only=["templates/flower/flower-service.yaml"],
        )

        assert bool(docs) is created
        if created:
            assert jmespath.search("metadata.name", docs[0]) == "release-name-flower"

    def test_default_service(self):
        docs = render_chart(
            values={"flower": {"enabled": True}},
            show_only=["templates/flower/flower-service.yaml"],
        )

        assert jmespath.search("metadata.name", docs[0]) == "release-name-flower"
        assert jmespath.search("metadata.annotations", docs[0]) is None
        assert jmespath.search("spec.selector", docs[0]) == {
            "tier": "airflow",
            "component": "flower",
            "release": "release-name",
        }
        assert jmespath.search("spec.type", docs[0]) == "ClusterIP"
        assert {"name": "flower-ui", "port": 5555} in jmespath.search("spec.ports", docs[0])

    def test_overrides(self):
        docs = render_chart(
            values={
                "ports": {"flowerUI": 9000},
                "flower": {
                    "enabled": True,
                    "service": {
                        "type": "LoadBalancer",
                        "loadBalancerIP": "127.0.0.1",
                        "annotations": {"foo": "bar"},
                        "loadBalancerSourceRanges": ["10.123.0.0/16"],
                    },
                },
            },
            show_only=["templates/flower/flower-service.yaml"],
        )

        assert jmespath.search("metadata.annotations", docs[0]) == {"foo": "bar"}
        assert jmespath.search("spec.type", docs[0]) == "LoadBalancer"
        assert {"name": "flower-ui", "port": 9000} in jmespath.search("spec.ports", docs[0])
        assert jmespath.search("spec.loadBalancerIP", docs[0]) == "127.0.0.1"
        assert jmespath.search("spec.loadBalancerSourceRanges", docs[0]) == ["10.123.0.0/16"]

    @pytest.mark.parametrize(
        "ports, expected_ports",
        [
            ([{"port": 8888}], [{"port": 8888}]),  # name is optional with a single port
            (
                [{"name": "{{ .Release.Name }}", "protocol": "UDP", "port": "{{ .Values.ports.flowerUI }}"}],
                [{"name": "release-name", "protocol": "UDP", "port": 5555}],
            ),
            ([{"name": "only_sidecar", "port": "{{ int 9000 }}"}], [{"name": "only_sidecar", "port": 9000}]),
            (
                [
                    {"name": "flower-ui", "port": "{{ .Values.ports.flowerUI }}"},
                    {"name": "sidecar", "port": 80, "targetPort": "sidecar"},
                ],
                [
                    {"name": "flower-ui", "port": 5555},
                    {"name": "sidecar", "port": 80, "targetPort": "sidecar"},
                ],
            ),
        ],
    )
    def test_ports_overrides(self, ports, expected_ports):
        docs = render_chart(
            values={
                "flower": {"enabled": True, "service": {"ports": ports}},
            },
            show_only=["templates/flower/flower-service.yaml"],
        )

        assert expected_ports == jmespath.search("spec.ports", docs[0])

    def test_should_add_component_specific_labels(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "labels": {"test_label": "test_label_value"},
                },
            },
            show_only=["templates/flower/flower-service.yaml"],
        )

        assert "test_label" in jmespath.search("metadata.labels", docs[0])
        assert jmespath.search("metadata.labels", docs[0])["test_label"] == "test_label_value"


class TestFlowerNetworkPolicy:
    """Tests flower network policy."""

    def test_off_by_default(self):
        docs = render_chart(
            show_only=["templates/flower/flower-networkpolicy.yaml"],
        )
        assert len(docs) == 0

    def test_defaults(self):
        docs = render_chart(
            values={
                "networkPolicies": {"enabled": True},
                "flower": {
                    "enabled": True,
                    "networkPolicy": {
                        "ingress": {
                            "from": [{"namespaceSelector": {"matchLabels": {"release": "myrelease"}}}]
                        }
                    },
                },
            },
            show_only=["templates/flower/flower-networkpolicy.yaml"],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "NetworkPolicy"
        assert jmespath.search("spec.ingress[0].from", docs[0]) == [
            {"namespaceSelector": {"matchLabels": {"release": "myrelease"}}}
        ]
        assert jmespath.search("spec.ingress[0].ports", docs[0]) == [{"port": 5555}]

    @pytest.mark.parametrize(
        "ports, expected_ports",
        [
            ([{"port": "sidecar"}], [{"port": "sidecar"}]),
            (
                [
                    {"port": "{{ .Values.ports.flowerUI }}"},
                    {"port": 80},
                ],
                [
                    {"port": 5555},
                    {"port": 80},
                ],
            ),
        ],
    )
    def test_ports_overrides(self, ports, expected_ports):
        docs = render_chart(
            values={
                "networkPolicies": {"enabled": True},
                "flower": {
                    "enabled": True,
                    "networkPolicy": {
                        "ingress": {
                            "from": [{"namespaceSelector": {"matchLabels": {"release": "myrelease"}}}],
                            "ports": ports,
                        }
                    },
                },
            },
            show_only=["templates/flower/flower-networkpolicy.yaml"],
        )

        assert expected_ports == jmespath.search("spec.ingress[0].ports", docs[0])

    def test_deprecated_from_param(self):
        docs = render_chart(
            values={
                "networkPolicies": {"enabled": True},
                "flower": {
                    "enabled": True,
                    "extraNetworkPolicies": [
                        {"namespaceSelector": {"matchLabels": {"release": "myrelease"}}}
                    ],
                },
            },
            show_only=["templates/flower/flower-networkpolicy.yaml"],
        )

        assert jmespath.search("spec.ingress[0].from", docs[0]) == [
            {"namespaceSelector": {"matchLabels": {"release": "myrelease"}}}
        ]

    def test_should_add_component_specific_labels(self):
        docs = render_chart(
            values={
                "networkPolicies": {"enabled": True},
                "flower": {
                    "enabled": True,
                    "labels": {"test_label": "test_label_value"},
                },
            },
            show_only=["templates/flower/flower-networkpolicy.yaml"],
        )

        assert "test_label" in jmespath.search("metadata.labels", docs[0])
        assert jmespath.search("metadata.labels", docs[0])["test_label"] == "test_label_value"


class TestFlowerServiceAccount:
    """Tests flower service account."""

    def test_should_add_component_specific_labels(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "labels": {"test_label": "test_label_value"},
                },
            },
            show_only=["templates/flower/flower-serviceaccount.yaml"],
        )

        assert "test_label" in jmespath.search("metadata.labels", docs[0])
        assert jmespath.search("metadata.labels", docs[0])["test_label"] == "test_label_value"

    def test_default_automount_service_account_token(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "serviceAccount": {
                        "create": True,
                    },
                }
            },
            show_only=["templates/flower/flower-serviceaccount.yaml"],
        )
        assert jmespath.search("automountServiceAccountToken", docs[0]) is True

    def test_overridden_automount_service_account_token(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "serviceAccount": {"create": True, "automountServiceAccountToken": False},
                }
            },
            show_only=["templates/flower/flower-serviceaccount.yaml"],
        )
        assert jmespath.search("automountServiceAccountToken", docs[0]) is False


class TestFlowerSecret:
    """Tests flower secret."""

    def test_should_add_annotations_to_flower_secret(self):
        docs = render_chart(
            values={
                "flower": {
                    "enabled": True,
                    "username": "username",
                    "password": "password",
                    "secretAnnotations": {"test_annotation": "test_annotation_value"},
                }
            },
            show_only=["templates/secrets/flower-secret.yaml"],
        )[0]

        assert "annotations" in jmespath.search("metadata", docs)
        assert jmespath.search("metadata.annotations", docs)["test_annotation"] == "test_annotation_value"
