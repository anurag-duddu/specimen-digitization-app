"""Exercise committed index DDL/catalog query against a disposable local server."""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

import pytest

import deploy_data


@pytest.mark.skipif(any(shutil.which(tool) is None for tool in ("initdb", "pg_ctl", "psql")) or os.geteuid() == 0,
                    reason="requires non-root disposable local PostgreSQL tools; never connects to production")
def test_native_index_catalog_matches_ddl_and_rejects_valid_wrong_same_name(tmp_path):
    def command(args, **kwargs):
        return subprocess.run(args, check=True, capture_output=True, timeout=30, **kwargs).stdout
    data = tmp_path / "pgdata"
    command(["initdb", "-D", str(data), "-A", "trust", "-U", "release_test"])
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    command(["pg_ctl", "-D", str(data), "-l", str(tmp_path / "postgres.log"), "-o",
             f"-p {port} -h 127.0.0.1 -c unix_socket_directories='' -c fsync=off", "-w", "start"])
    try:
        def sql(statement, database="postgres", user="release_test"):
            return command(["psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", str(port),
                            "-U", user, "-d", database, "-qAt", "-c", statement]).decode().strip()
        sql("""CREATE TABLE specimen (organization_id uuid, collection_id uuid, id uuid, created_at timestamptz,
          revision integer, state text, disposition text, work_available_at timestamptz, active_run_id uuid,
          sensitive boolean, source_checksum text);
          CREATE TABLE auxiliary_document (organization_id uuid, collection_id uuid, id uuid, kind text,
          created_at timestamptz, revision integer);
          CREATE TABLE specimen_snapshot (organization_id uuid, collection_id uuid, specimen_id uuid,
          revision integer, snapshot jsonb);
          CREATE UNIQUE INDEX specimen_scope_checksum ON specimen (organization_id,collection_id,source_checksum);""")
        for filename in ("paging-indexes.sql", "search-indexes.sql"):
            source = re.sub(r"^\s*--.*$", "", (deploy_data.ROOT / "dataconnect/sql" / filename).read_text(), flags=re.M)
            for statement in source.split(";"):
                if statement.strip():
                    sql(statement)
        script = Path(__file__).with_name("release_sql.mjs").read_text()
        query = re.search(r"const indexes = \(await client.query\(`(.*?)`\)\).rows;", script, re.S).group(1)
        def inventory():
            return {"indexes": json.loads(sql("SELECT json_agg(x) FROM (" + query + ") x"))}
        observed = inventory()
        (tmp_path / "index-catalog.json").write_text(json.dumps(observed, indent=2))
        deploy_data.verify_indexes(observed)
        sql("DROP INDEX specimen_text_cursor")
        sql("CREATE INDEX specimen_text_cursor ON specimen (id)")
        with pytest.raises(ValueError, match="definition"):
            deploy_data.verify_indexes(inventory())
        catalog = Path(__file__).with_name("release_sql_catalog.sql").read_text()
        with pytest.raises(subprocess.CalledProcessError):
            sql(catalog, "template1")  # Neither approved control nor application DB.
        sql('CREATE ROLE "specimen-data-release@specimen-digitization.iam" LOGIN')
        # Use the exact committed SELECT within a JSON projection, preserving
        # BEGIN READ ONLY, both timeouts and the named-database guard.
        start, end = catalog.index("WITH approved"), catalog.index(";\nCOMMIT;")
        wrapped = catalog[:start] + "SELECT row_to_json(x) FROM (" + catalog[start:end] + ") x;\nCOMMIT;"
        result = sql(wrapped, "postgres", "specimen-data-release@specimen-digitization.iam")
        missing = deploy_data.validate_catalog(json.loads(result.splitlines()[-1]))
        assert missing["expected_actor"] and missing["expected_database"]
        assert missing["application_database_exists"] is False
        assert missing["application_catalog_observed"] is False
        # The control database has the three index fixtures above, but they are
        # not application observations and must never appear in this receipt.
        assert missing["approved_tables"] == [] and missing["public_table_count"] == 0
        wrong_actor = json.loads(sql(wrapped).splitlines()[-1])
        with pytest.raises(ValueError, match="maintenance identity"):
            deploy_data.validate_catalog(wrong_actor)
        sql('CREATE DATABASE "specimen-digitization-database"')
        result = sql(wrapped, deploy_data.DATABASE, "specimen-data-release@specimen-digitization.iam")
        metadata = deploy_data.validate_catalog(json.loads(result.splitlines()[-1]))
        assert metadata["expected_actor"] and metadata["expected_database"]
        assert metadata["application_database_exists"] and metadata["application_catalog_observed"]
        assert not metadata["owner_exists"] and metadata["approved_tables"] == []
        assert metadata["public_table_count"] == metadata["unapproved_table_count"] == 0
        with pytest.raises(subprocess.CalledProcessError):
            sql(catalog.replace("COMMIT;", "CREATE TABLE forbidden_catalog_write(id integer); COMMIT;"),
                deploy_data.DATABASE, "release_test")
        assert sql("SELECT count(*) FROM pg_tables WHERE schemaname='public'", deploy_data.DATABASE) == "0"
    finally:
        command(["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"])
