"""Dispatcherd task for processing metrics-utility archive imports.

Supports both .tar.gz and .zip files from the metrics-utility output.
Zip files contain a data/YYYY/MM/DD/ hierarchy with nested .tar.gz files,
each containing a CSV with a 2-line metadata header.

CSV types handled:
  - main_host.csv          → host inventory with canonical_facts (SMBIOS)
  - job_host_summary.csv   → per-job execution summaries
  - main_jobevent.csv      → granular task-level events
  - main_indirectmanagednodeaudit.csv → cloud/API-managed resources
"""

import csv
import io
import json
import logging
import tarfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

import django
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger('apps.inventory.tasks')

try:
    from apps.inventory.dispatcher import setup_dispatcher
    setup_dispatcher()
    from dispatcherd.publish import task
except ImportError:
    logger.debug('dispatcherd not available')

    def task(*args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper


def _ensure_django():
    try:
        django.setup()
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Date / helper parsing
# ---------------------------------------------------------------------------

def _is_ip_address(value):
    parts = value.split('.')
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _parse_datetime(value):
    if not value or not value.strip():
        return None
    value = value.strip()
    # Handle timezone suffixes like +00:00, +0000, +00 or Z
    for suffix in ('+00:00', '+0000', '+00', 'Z'):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
            break
    for fmt in (
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d',
    ):
        try:
            return timezone.make_aware(datetime.strptime(value, fmt))
        except (ValueError, TypeError):
            continue
    return None


def _safe_json(value):
    """Try to parse a JSON string; return original or empty dict on failure."""
    if not value or not value.strip():
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _safe_json_list(value):
    """Parse a JSON list string; return list on success, empty list on failure."""
    if not value or not value.strip():
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else [result]
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Archive extraction — supports .zip (metrics-utility output) and .tar.gz
# ---------------------------------------------------------------------------

def _read_csv_text(text):
    """Parse CSV text, skipping the 2-line metadata header if present.

    Metrics-utility CSVs have a structure like:
      Line 1: collection_start_timestamp,since,until,file_name,status,elapsed
      Line 2: 2026-02-03 02:00:05...,2026-02-03 00:00:00...,... (metadata row)
      Line 3: actual_field1,actual_field2,...  (real header)
      Line 4+: data rows
    """
    lines = text.strip().split('\n')
    if len(lines) < 3:
        # Might be a simple CSV without metadata header
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    # Check if first line looks like the metrics-utility metadata header
    first_fields = [f.strip() for f in lines[0].split(',')]
    if 'collection_start_timestamp' in first_fields or 'file_name' in first_fields:
        # Skip first 2 lines (metadata header + metadata values)
        real_csv = '\n'.join(lines[2:])
        reader = csv.DictReader(io.StringIO(real_csv))
        return list(reader)
    else:
        # Normal CSV
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)


def _extract_csv_from_inner_targz(fileobj):
    """Extract CSV rows from an inner .tar.gz that contains a single CSV."""
    rows = []
    try:
        with tarfile.open(fileobj=fileobj, mode='r:*') as inner_tar:
            for member in inner_tar.getmembers():
                if member.name.endswith('.csv'):
                    f = inner_tar.extractfile(member)
                    if f:
                        text = f.read().decode('utf-8', errors='replace')
                        rows.extend(_read_csv_text(text))
    except tarfile.TarError:
        pass
    return rows


def _classify_csv(filename):
    """Determine CSV type from filename."""
    name_lower = filename.lower()
    if 'main_host' in name_lower:
        return 'main_host'
    elif 'job_host_summary' in name_lower:
        return 'job_host_summary'
    elif 'indirectmanagednodeaudit' in name_lower:
        return 'indirect_audit'
    elif 'jobevent' in name_lower:
        return 'job_event'
    return 'unknown'


def _extract_from_zip(file_path):
    """Extract CSVs from a metrics-utility zip file.

    Structure: data/YYYY/MM/DD/{uuid}-{dates}-{seq}-{table}.tar.gz
    Each tar.gz contains a single CSV file.
    """
    categorised = {
        'main_host': [],
        'job_host_summary': [],
        'indirect_audit': [],
        'job_event': [],
    }
    csv_count = 0

    with zipfile.ZipFile(file_path, 'r') as zf:
        for entry in zf.namelist():
            # Skip __MACOSX metadata
            if '__MACOSX' in entry:
                continue

            if entry.endswith('.tar.gz') or entry.endswith('.tgz'):
                csv_type = _classify_csv(entry)
                if csv_type == 'unknown':
                    continue

                with zf.open(entry) as inner_file:
                    rows = _extract_csv_from_inner_targz(io.BytesIO(inner_file.read()))
                    if rows:
                        categorised[csv_type].extend(rows)
                        csv_count += 1

            elif entry.endswith('.csv'):
                csv_type = _classify_csv(entry)
                if csv_type == 'unknown':
                    continue
                with zf.open(entry) as f:
                    text = f.read().decode('utf-8', errors='replace')
                    rows = _read_csv_text(text)
                    if rows:
                        categorised[csv_type].extend(rows)
                        csv_count += 1

    return categorised, csv_count


def _extract_from_tarball(file_path):
    """Extract CSVs from a tarball (original .tar.gz format)."""
    categorised = {
        'main_host': [],
        'job_host_summary': [],
        'indirect_audit': [],
        'job_event': [],
    }
    csv_count = 0

    with tarfile.open(file_path, 'r:*') as tar:
        for member in tar.getmembers():
            if member.name.endswith('.csv'):
                csv_type = _classify_csv(member.name)
                if csv_type == 'unknown':
                    continue
                f = tar.extractfile(member)
                if f:
                    text = f.read().decode('utf-8', errors='replace')
                    rows = _read_csv_text(text)
                    if rows:
                        categorised[csv_type].extend(rows)
                        csv_count += 1

            elif member.name.endswith('.tar.gz') or member.name.endswith('.tgz'):
                csv_type = _classify_csv(member.name)
                if csv_type == 'unknown':
                    continue
                outer_f = tar.extractfile(member)
                if outer_f:
                    rows = _extract_csv_from_inner_targz(outer_f)
                    if rows:
                        categorised[csv_type].extend(rows)
                        csv_count += 1

    return categorised, csv_count


def _extract_archive(file_path):
    """Auto-detect archive format and extract categorised CSVs."""
    fp = str(file_path)

    if zipfile.is_zipfile(fp):
        logger.info('Detected zip archive: %s', fp)
        return _extract_from_zip(fp)

    # Try as tarball
    try:
        with tarfile.open(fp, 'r:*'):
            pass
        logger.info('Detected tarball archive: %s', fp)
        return _extract_from_tarball(fp)
    except tarfile.TarError:
        pass

    raise ValueError(f'Unrecognised archive format: {fp}')


# ---------------------------------------------------------------------------
# Host roster building — enriched with SMBIOS and job data
# ---------------------------------------------------------------------------

def _build_enriched_roster(categorised):
    """Build a comprehensive host roster from all CSV types.

    Returns:
        roster: dict keyed by hostname with SMBIOS, job summaries, etc.
        indirect_nodes: list of indirect managed node audit records
        total_rows: total CSV rows processed
    """
    roster = {}
    total_rows = 0

    def _ensure(hostname):
        if hostname not in roster:
            roster[hostname] = {
                'host_id': None,
                'canonical_facts': {},
                'facts': {},
                'inventory_name': '',
                'organization_name': '',
                'first_seen': None,
                'last_seen': None,
                'total_events': 0,
                'jobs': [],           # from job_host_summary
                'machine_id': None,   # SMBIOS UUID
                'product_serial': None,
                'system_vendor': None,
            }

    def _update_time(entry, dt):
        if dt:
            if entry['first_seen'] is None or dt < entry['first_seen']:
                entry['first_seen'] = dt
            if entry['last_seen'] is None or dt > entry['last_seen']:
                entry['last_seen'] = dt

    # --- 1. main_host.csv: richest data with canonical_facts ---
    for row in categorised.get('main_host', []):
        total_rows += 1
        hostname = (row.get('host_name') or '').strip()
        if not hostname:
            continue
        _ensure(hostname)
        entry = roster[hostname]

        entry['host_id'] = row.get('host_id') or entry['host_id']
        entry['inventory_name'] = row.get('inventory_name') or entry['inventory_name']
        entry['organization_name'] = row.get('organization_name') or entry['organization_name']

        # Parse canonical_facts — contains ansible_machine_id (SMBIOS UUID)
        cf = _safe_json(row.get('canonical_facts', ''))
        if cf:
            entry['canonical_facts'] = cf
            machine_id = cf.get('ansible_machine_id', '')
            if machine_id:
                entry['machine_id'] = machine_id.lower().strip()
            serial = cf.get('ansible_product_serial', '')
            if serial and serial != 'NA':
                entry['product_serial'] = serial.strip()

        # Parse facts — contains ansible_system_vendor, ansible_product_name etc
        facts = _safe_json(row.get('facts', ''))
        if facts:
            entry['facts'] = facts
            vendor = facts.get('ansible_system_vendor', '')
            if vendor:
                entry['system_vendor'] = vendor.strip()

        dt = _parse_datetime(row.get('last_automation', ''))
        _update_time(entry, dt)

    # --- 2. job_host_summary.csv: per-job execution data ---
    for row in categorised.get('job_host_summary', []):
        total_rows += 1
        hostname = (row.get('host_name') or '').strip()
        if not hostname:
            continue
        _ensure(hostname)
        entry = roster[hostname]

        job_info = {
            'job_remote_id': int(row.get('job_remote_id', 0) or 0),
            'job_template_remote_id': int(row.get('job_template_remote_id', 0) or 0),
            'job_template_name': (row.get('job_template_name') or '').strip(),
            'inventory_name': (row.get('inventory_name') or '').strip(),
            'organization_name': (row.get('organization_name') or '').strip(),
            'project_name': (row.get('project_name') or '').strip(),
            'ok': int(row.get('ok', 0) or 0),
            'changed': int(row.get('changed', 0) or 0),
            'failures': int(row.get('failures', 0) or 0),
            'dark': int(row.get('dark', 0) or 0),
            'skipped': int(row.get('skipped', 0) or 0),
            'failed': row.get('failed', 'f') == 't',
            'job_created': _parse_datetime(row.get('job_created', '')),
        }

        # Deduplicate jobs by job_remote_id
        existing_ids = {j['job_remote_id'] for j in entry['jobs']}
        if job_info['job_remote_id'] and job_info['job_remote_id'] not in existing_ids:
            entry['jobs'].append(job_info)

        entry['inventory_name'] = job_info['inventory_name'] or entry['inventory_name']
        entry['organization_name'] = job_info['organization_name'] or entry['organization_name']

        dt = job_info['job_created']
        _update_time(entry, dt)

    # --- 3. main_jobevent.csv: task-level events (aggregate counts per host) ---
    for row in categorised.get('job_event', []):
        total_rows += 1
        hostname = (row.get('host_name') or '').strip()
        if not hostname:
            continue
        _ensure(hostname)
        entry = roster[hostname]
        entry['total_events'] += 1

        dt = _parse_datetime(row.get('created') or row.get('modified', ''))
        _update_time(entry, dt)

    # --- 4. main_indirectmanagednodeaudit.csv: indirect (cloud) resources ---
    indirect_nodes = []
    for row in categorised.get('indirect_audit', []):
        total_rows += 1
        node_name = (row.get('host_name') or '').strip()
        if not node_name:
            continue
        indirect_nodes.append({
            'host_name': node_name,
            'canonical_facts': _safe_json(row.get('canonical_facts', '')),
            'facts': _safe_json(row.get('facts', '')),
            'events': _safe_json_list(row.get('events', '')),
            'task_runs': int(row.get('task_runs', 0) or 0),
            'job_remote_id': int(row.get('job_remote_id', 0) or 0),
            'job_template_name': (row.get('job_template_name') or '').strip(),
            'inventory_name': (row.get('inventory_name') or '').strip(),
            'organization_name': (row.get('organization_name') or '').strip(),
            'project_name': (row.get('project_name') or '').strip(),
            'job_created': _parse_datetime(row.get('job_created', '')),
        })

    return roster, indirect_nodes, total_rows


# ---------------------------------------------------------------------------
# Matching strategies
# ---------------------------------------------------------------------------

AUTO_MATCH_THRESHOLD = 80


def _match_host_to_resource(hostname, host_data, org_id, learned_mappings, source_label):
    """Multi-strategy matching: learned → SMBIOS → name/FQDN → IP → fuzzy.

    SMBIOS matching compares the ansible_machine_id from metrics canonical_facts
    against Resource.canonical_id and Resource.vendor_identifiers values.
    """
    from apps.inventory.models import Resource

    # --- Strategy 0: Learned mappings (fastest) ---
    mapping_key = (hostname, source_label)
    global_key = (hostname, '')
    if mapping_key in learned_mappings:
        return learned_mappings[mapping_key], 100, 'learned mapping (source-specific)'
    if global_key in learned_mappings:
        return learned_mappings[global_key], 100, 'learned mapping (global)'

    base_qs = Resource.objects.filter(organization_id=org_id, deleted_at__isnull=True)

    # --- Strategy 1: SMBIOS / machine_id match (hardware-unique) ---
    machine_id = host_data.get('machine_id')
    if machine_id and len(machine_id) >= 8:
        # Match against canonical_id (primary SMBIOS field)
        smbios_match = base_qs.filter(canonical_id__iexact=machine_id)
        if smbios_match.count() == 1:
            return smbios_match.first(), 98, f'SMBIOS machine_id match (canonical_id={machine_id})'

        # Match against vendor_identifiers JSONB — check common keys
        # vendor_identifiers might have: bios_uuid, smbios_uuid, instance_uuid, machine_id
        for vi_key in ('bios_uuid', 'smbios_uuid', 'instance_uuid', 'machine_id'):
            vi_match = base_qs.filter(**{f'vendor_identifiers__{vi_key}__iexact': machine_id})
            if vi_match.count() == 1:
                return vi_match.first(), 96, f'SMBIOS machine_id match (vendor_identifiers.{vi_key}={machine_id})'

        # Also try matching the product_serial if we have it
        product_serial = host_data.get('product_serial')
        if product_serial and product_serial != 'NA' and len(product_serial) >= 6:
            serial_match = base_qs.filter(
                Q(canonical_id__iexact=product_serial) |
                Q(vendor_identifiers__serial_number__iexact=product_serial) |
                Q(vendor_identifiers__product_serial__iexact=product_serial)
            )
            if serial_match.count() == 1:
                return serial_match.first(), 92, f'product serial match ({product_serial})'

    # --- Strategy 2: Exact name / FQDN / ansible_host match ---
    exact_name = base_qs.filter(name__iexact=hostname)
    if exact_name.count() == 1:
        return exact_name.first(), 95, 'exact name match'

    exact_fqdn = base_qs.filter(fqdn__iexact=hostname)
    if exact_fqdn.count() == 1:
        return exact_fqdn.first(), 95, 'exact FQDN match'

    exact_ansible = base_qs.filter(ansible_host__iexact=hostname)
    if exact_ansible.count() == 1:
        return exact_ansible.first(), 95, 'exact ansible_host match'

    # --- Strategy 3: IP address match ---
    if _is_ip_address(hostname):
        ip_match = base_qs.filter(ip_addresses__contains=[hostname])
        if ip_match.count() == 1:
            return ip_match.first(), 90, 'IP address match'
        ip_ansible = base_qs.filter(ansible_host=hostname)
        if ip_ansible.count() == 1:
            return ip_ansible.first(), 90, 'ansible_host IP match'

    # --- Strategy 4: Hostname prefix / FQDN short name ---
    if not _is_ip_address(hostname) and '.' not in hostname:
        prefix_match = base_qs.filter(
            Q(fqdn__istartswith=hostname + '.') |
            Q(name__istartswith=hostname + '.')
        )
        if prefix_match.count() == 1:
            return prefix_match.first(), 70, 'hostname prefix of FQDN'

    if '.' in hostname:
        short_name = hostname.split('.')[0]
        short_match = base_qs.filter(name__iexact=short_name)
        if short_match.count() == 1:
            return short_match.first(), 65, 'FQDN short name matches resource'

    # --- Strategy 5: Partial / fuzzy match ---
    if len(hostname) >= 4 and not _is_ip_address(hostname):
        contains_match = base_qs.filter(
            Q(name__icontains=hostname) |
            Q(fqdn__icontains=hostname) |
            Q(ansible_host__icontains=hostname)
        )
        if contains_match.count() == 1:
            return contains_match.first(), 40, 'partial name/FQDN contains match'
        elif contains_match.count() > 1:
            return contains_match.first(), 25, f'ambiguous contains match ({contains_match.count()} candidates)'

    return None, 0, ''


def _match_indirect_node(node, org_id):
    """Try to match an indirect managed node to an inventory Resource.

    Indirect nodes are cloud resources identified by vendor IDs (e.g. VMware moid,
    Azure resource ID) rather than hostname.
    """
    from apps.inventory.models import Resource

    base_qs = Resource.objects.filter(organization_id=org_id, deleted_at__isnull=True)
    cf = node.get('canonical_facts', {})
    host_name = node.get('host_name', '')

    # Try moid match (VMware)
    moid = cf.get('moid', '')
    if moid:
        moid_match = base_qs.filter(
            Q(vendor_identifiers__moid=moid) |
            Q(canonical_id__iexact=moid)
        )
        if moid_match.count() == 1:
            return moid_match.first(), 96, f'VMware moid match ({moid})'

    # Try Azure resource ID match
    azure_id = cf.get('id', '')
    if azure_id and azure_id.startswith('/subscriptions/'):
        azure_match = base_qs.filter(
            Q(vendor_identifiers__resource_id__iexact=azure_id) |
            Q(canonical_id__iexact=azure_id)
        )
        if azure_match.count() == 1:
            return azure_match.first(), 96, f'Azure resource ID match'

        # Try matching by resource name (last segment of the Azure ID)
        resource_name = azure_id.rsplit('/', 1)[-1]
        if resource_name:
            name_match = base_qs.filter(name__iexact=resource_name)
            if name_match.count() == 1:
                return name_match.first(), 70, f'Azure resource name match ({resource_name})'

    # Try by host_name (e.g. vm-13320 for VMware)
    if host_name and not host_name.startswith('/'):
        name_match = base_qs.filter(
            Q(name__iexact=host_name) |
            Q(vendor_identifiers__moid=host_name)
        )
        if name_match.count() == 1:
            return name_match.first(), 85, f'indirect node name match ({host_name})'

    return None, 0, ''


# ---------------------------------------------------------------------------
# Main processing task
# ---------------------------------------------------------------------------

@task(queue='inventory')
def process_metrics_import(metrics_import_id):
    """Process an uploaded metrics-utility archive (zip or tarball)."""
    _ensure_django()

    from apps.inventory.models import AutomationRecord
    from apps.inventory.models.metrics_import import (
        HostMapping, MetricsImport, PendingMatch,
    )

    try:
        imp = MetricsImport.objects.get(pk=metrics_import_id)
    except MetricsImport.DoesNotExist:
        logger.error('MetricsImport %s not found', metrics_import_id)
        return {'error': f'MetricsImport {metrics_import_id} not found'}

    if imp.status != MetricsImport.Status.PENDING:
        logger.warning('MetricsImport %s already %s', imp.pk, imp.status)
        return {'skipped': True, 'status': imp.status}

    imp.status = MetricsImport.Status.PROCESSING
    imp.save(update_fields=['status'])
    logger.info('Processing metrics import: %s (%s)', imp.filename, imp.pk)

    errors = []
    stats = {
        'csvs_found': 0,
        'total_csv_rows': 0,
        'unique_hosts': 0,
        'auto_matched': 0,
        'pending_review': 0,
        'unmatched': 0,
        'automation_records_created': 0,
        'learned_mapping_hits': 0,
        'indirect_nodes_found': 0,
        'indirect_matched': 0,
        'hosts_with_smbios': 0,
        'smbios_matches': 0,
        'jobs_found': 0,
    }

    try:
        # --- Extract archive ---
        categorised, csv_count = _extract_archive(imp.file_path)
        stats['csvs_found'] = csv_count
        logger.info('Extracted %d CSV files from archive', csv_count)

        if not any(categorised.values()):
            errors.append('No recognised CSV data found in the archive.')
            imp.status = MetricsImport.Status.FAILED
            imp.error_log = '\n'.join(errors)
            imp.stats = stats
            imp.processed_at = timezone.now()
            imp.save(update_fields=['status', 'error_log', 'stats', 'processed_at'])
            return {'error': 'No CSV data found'}

        # --- Build enriched roster ---
        roster, indirect_nodes, total_rows = _build_enriched_roster(categorised)
        stats['total_csv_rows'] = total_rows
        stats['unique_hosts'] = len(roster)
        stats['indirect_nodes_found'] = len(indirect_nodes)
        stats['hosts_with_smbios'] = sum(1 for h in roster.values() if h.get('machine_id'))
        stats['jobs_found'] = sum(len(h.get('jobs', [])) for h in roster.values())
        logger.info(
            'Roster: %d hosts (%d with SMBIOS), %d indirect nodes, %d total jobs',
            len(roster), stats['hosts_with_smbios'], len(indirect_nodes), stats['jobs_found'],
        )

        # --- Load learned mappings ---
        mappings_qs = HostMapping.objects.filter(
            organization=imp.organization,
        ).select_related('resource')
        learned_mappings = {(m.aap_host_name, m.source_label): m.resource for m in mappings_qs}

        # --- Match hosts and create records ---
        auto_records = []
        pending_records = []

        for hostname, host_data in roster.items():
            resource, confidence, reason = _match_host_to_resource(
                hostname, host_data, imp.organization_id, learned_mappings, imp.source_label,
            )

            if 'SMBIOS' in reason or 'machine_id' in reason:
                stats['smbios_matches'] += 1

            raw = {
                'total_events': host_data.get('total_events', 0),
                'first_seen': host_data['first_seen'].isoformat() if host_data.get('first_seen') else None,
                'last_seen': host_data['last_seen'].isoformat() if host_data.get('last_seen') else None,
                'machine_id': host_data.get('machine_id'),
                'product_serial': host_data.get('product_serial'),
                'system_vendor': host_data.get('system_vendor'),
                'inventory_name': host_data.get('inventory_name', ''),
                'organization_name': host_data.get('organization_name', ''),
                'jobs_count': len(host_data.get('jobs', [])),
            }

            if confidence >= AUTO_MATCH_THRESHOLD and resource is not None:
                stats['auto_matched'] += 1
                if reason.startswith('learned'):
                    stats['learned_mapping_hits'] += 1

                # Create per-job AutomationRecords if we have job data
                jobs = host_data.get('jobs', [])
                if jobs:
                    for job in jobs:
                        auto_records.append(AutomationRecord(
                            resource=resource,
                            source_name=imp.source_label or imp.filename,
                            correlation_type='direct',
                            correlation_key=f'smbios:{host_data["machine_id"]}' if host_data.get('machine_id')
                                            else f'hostname:{hostname}',
                            correlation_confidence='exact' if confidence >= 90 else 'probable',
                            aap_host_id=int(host_data.get('host_id') or 0) or None,
                            aap_host_name=hostname,
                            aap_job_id=job['job_remote_id'],
                            aap_job_name=job['job_template_name'],
                            aap_job_status='failed' if job.get('failed') else 'successful',
                            aap_job_started_at=job.get('job_created'),
                            aap_job_finished_at=job.get('job_created'),  # summary doesn't have end time
                            aap_inventory_name=job.get('inventory_name', ''),
                            automation_details={
                                'import_id': str(imp.pk),
                                'match_reason': reason,
                                'match_confidence': confidence,
                                'project_name': job.get('project_name', ''),
                                'ok': job.get('ok', 0),
                                'changed': job.get('changed', 0),
                                'failures': job.get('failures', 0),
                                'dark': job.get('dark', 0),
                                'skipped': job.get('skipped', 0),
                            },
                            organization=imp.organization,
                        ))
                else:
                    # No individual job data — create a single aggregated record
                    auto_records.append(AutomationRecord(
                        resource=resource,
                        source_name=imp.source_label or imp.filename,
                        correlation_type='direct',
                        correlation_key=f'smbios:{host_data["machine_id"]}' if host_data.get('machine_id')
                                        else f'hostname:{hostname}',
                        correlation_confidence='exact' if confidence >= 90 else 'probable',
                        aap_host_id=int(host_data.get('host_id') or 0) or None,
                        aap_host_name=hostname,
                        aap_job_id=0,
                        aap_job_name=f'Metrics import: {imp.filename}',
                        aap_job_status='aggregated',
                        aap_job_started_at=host_data.get('first_seen'),
                        aap_job_finished_at=host_data.get('last_seen'),
                        aap_inventory_name=host_data.get('inventory_name', ''),
                        automation_details={
                            'import_id': str(imp.pk),
                            'match_reason': reason,
                            'match_confidence': confidence,
                            **raw,
                        },
                        organization=imp.organization,
                    ))

            elif resource is not None and confidence > 0:
                stats['pending_review'] += 1
                pending_records.append(PendingMatch(
                    metrics_import=imp, aap_host_name=hostname,
                    candidate_resource=resource, match_reason=reason,
                    match_score=confidence, raw_data=raw,
                ))
            else:
                stats['unmatched'] += 1
                pending_records.append(PendingMatch(
                    metrics_import=imp, aap_host_name=hostname,
                    candidate_resource=None, match_reason='no match found',
                    match_score=0, raw_data=raw,
                ))

        # --- Match indirect nodes (VMware VMs, Azure resources, etc.) ---
        indirect_auto_records = []
        for node in indirect_nodes:
            resource, confidence, reason = _match_indirect_node(node, imp.organization_id)
            if confidence >= AUTO_MATCH_THRESHOLD and resource is not None:
                stats['indirect_matched'] += 1
                indirect_auto_records.append(AutomationRecord(
                    resource=resource,
                    source_name=imp.source_label or imp.filename,
                    correlation_type='indirect',
                    correlation_key=f'indirect:{node["host_name"]}',
                    correlation_confidence='exact' if confidence >= 90 else 'probable',
                    aap_host_name=node['host_name'],
                    aap_job_id=node.get('job_remote_id', 0),
                    aap_job_name=node.get('job_template_name', ''),
                    aap_job_status='successful',
                    aap_job_started_at=node.get('job_created'),
                    aap_job_finished_at=node.get('job_created'),
                    aap_inventory_name=node.get('inventory_name', ''),
                    automation_details={
                        'import_id': str(imp.pk),
                        'match_reason': reason,
                        'match_confidence': confidence,
                        'infra_type': node.get('facts', {}).get('infra_type', ''),
                        'device_type': node.get('facts', {}).get('device_type', ''),
                        'infra_bucket': node.get('facts', {}).get('infra_bucket', ''),
                        'collections_used': node.get('events', []),
                        'task_runs': node.get('task_runs', 0),
                        'project_name': node.get('project_name', ''),
                    },
                    organization=imp.organization,
                ))

        # --- Bulk create records ---
        all_auto_records = auto_records + indirect_auto_records
        if all_auto_records:
            created = AutomationRecord.objects.bulk_create(all_auto_records, ignore_conflicts=True)
            stats['automation_records_created'] = len(created)
            logger.info('Created %d AutomationRecords (%d direct, %d indirect)',
                        len(created), len(auto_records), len(indirect_auto_records))

        if pending_records:
            PendingMatch.objects.bulk_create(pending_records)
            logger.info('Created %d PendingMatch records', len(pending_records))

        # --- Done ---
        imp.status = MetricsImport.Status.COMPLETED
        imp.stats = stats
        imp.error_log = '\n'.join(errors) if errors else ''
        imp.processed_at = timezone.now()
        imp.save(update_fields=['status', 'stats', 'error_log', 'processed_at'])
        logger.info('MetricsImport %s completed: %s', imp.pk, stats)
        return stats

    except Exception as exc:
        imp.status = MetricsImport.Status.FAILED
        imp.error_log = f'{exc}\n\n{traceback.format_exc()}'
        imp.stats = stats
        imp.processed_at = timezone.now()
        imp.save(update_fields=['status', 'error_log', 'stats', 'processed_at'])
        logger.exception('MetricsImport %s failed', imp.pk)
        return {'error': str(exc)}
