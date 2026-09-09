-- Read only; full private catalog facts are hashed, never replaced with emptiness.
SELECT jsonb_build_object(
  'server_major', current_setting('server_version_num')::integer / 10000,
  'databases', (SELECT jsonb_agg(jsonb_build_object('name', datname,
    'owner', pg_get_userbyid(datdba), 'encoding', encoding, 'collation', datcollate,
    'ctype', datctype, 'locale_provider', datlocprovider, 'locale', datlocale,
    'collation_version', datcollversion, 'acl', datacl::text) ORDER BY datname)
    FROM pg_database WHERE NOT datistemplate),
  'roles', (SELECT jsonb_agg(jsonb_build_object('name', rolname, 'login', rolcanlogin,
    'super', rolsuper, 'create_role', rolcreaterole, 'create_db', rolcreatedb,
    'replication', rolreplication, 'bypass_rls', rolbypassrls, 'inherit', rolinherit,
    'config', rolconfig, 'connection_limit', rolconnlimit, 'valid_until', rolvaliduntil) ORDER BY rolname)
    FROM pg_roles),
  'memberships', COALESCE((SELECT jsonb_agg(jsonb_build_object('role', r.rolname,
    'member', u.rolname, 'grantor', g.rolname, 'admin', m.admin_option,
    'inherit', m.inherit_option, 'set', m.set_option) ORDER BY r.rolname,u.rolname,g.rolname)
    FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member
    JOIN pg_roles g ON g.oid=m.grantor), '[]'::jsonb),
  'namespaces', (SELECT jsonb_agg(jsonb_build_object('name', nspname,
    'owner', pg_get_userbyid(nspowner), 'acl', nspacl::text) ORDER BY nspname)
    FROM pg_namespace WHERE left(nspname,3) <> 'pg_' AND nspname <> 'information_schema'),
  'user_relations', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema'),
  'user_routines', (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema'),
  'user_types', (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
    WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema'),
  'event_triggers',(SELECT count(*) FROM pg_event_trigger),
  'publications',(SELECT count(*) FROM pg_publication),
  'foreign_servers',(SELECT count(*) FROM pg_foreign_server),
  'foreign_wrappers',(SELECT count(*) FROM pg_foreign_data_wrapper),
  'large_objects',(SELECT count(*) FROM pg_largeobject_metadata),
  'extensions', (SELECT jsonb_agg(jsonb_build_object('name', extname,'version',extversion) ORDER BY extname) FROM pg_extension)
) AS catalog;
