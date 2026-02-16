"""Add physical_server and orchestration_stack resource types + vendor mappings."""
from django.db import migrations


def seed_missing_types(apps, schema_editor):
    ResourceType = apps.get_model("inventory", "ResourceType")
    ResourceCategory = apps.get_model("inventory", "ResourceCategory")
    VendorTypeMapping = apps.get_model("inventory", "VendorTypeMapping")

    compute = ResourceCategory.objects.get(slug="compute")
    app_int = ResourceCategory.objects.get(slug="app_integration")

    # physical_server — bare-metal or managed physical hosts (OpenShift workers, etc.)
    ps, _ = ResourceType.objects.get_or_create(
        slug="physical_server",
        defaults={
            "category": compute,
            "name": "Physical Server",
            "description": "A physical server or managed node (e.g. OpenShift worker, bare-metal host).",
            "is_countable": True,
            "long_term_strategic_value": 4,
            "short_term_opportunity": 3,
            "sort_order": 45,
        },
    )

    # orchestration_stack — Heat, CloudFormation, ARM, Terraform state, etc.
    os_type, _ = ResourceType.objects.get_or_create(
        slug="orchestration_stack",
        defaults={
            "category": app_int,
            "name": "Orchestration Stack",
            "description": "A declarative infrastructure stack (Heat, CloudFormation, ARM template, etc.).",
            "is_countable": False,
            "long_term_strategic_value": 3,
            "short_term_opportunity": 2,
            "sort_order": 65,
        },
    )

    # Vendor type mappings
    mappings = [
        ("openshift", "Worker Node", ps, "kubernetes.core"),
        ("openshift", "Master Node", ps, "kubernetes.core"),
        ("vmware", "ESXi Host", ps, "vmware.vmware"),
        ("openstack", "Heat Stack", os_type, "openstack.cloud"),
        ("aws", "CloudFormation Stack", os_type, "amazon.aws"),
        ("azure", "ARM Deployment", os_type, "azure.azcollection"),
        ("gcp", "Deployment Manager", os_type, "google.cloud"),
    ]
    for vendor, vrt, rt, collection in mappings:
        VendorTypeMapping.objects.get_or_create(
            vendor=vendor,
            vendor_resource_type=vrt,
            defaults={
                "resource_type": rt,
                "ansible_collection": collection,
            },
        )


def remove_types(apps, schema_editor):
    ResourceType = apps.get_model("inventory", "ResourceType")
    VendorTypeMapping = apps.get_model("inventory", "VendorTypeMapping")
    for slug in ("physical_server", "orchestration_stack"):
        VendorTypeMapping.objects.filter(resource_type__slug=slug).delete()
        ResourceType.objects.filter(slug=slug).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0005_resource_fields_property_definitions"),
    ]
    operations = [
        migrations.RunPython(seed_missing_types, remove_types),
    ]
