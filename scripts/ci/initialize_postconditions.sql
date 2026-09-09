-- Runs before transaction commit, and again read-only under ordinary maintenance.
DO $postconditions$
DECLARE
  owner_role constant text := 'firebaseowner_specimen-digitization-database_public';
  writer_role constant text := 'firebasewriter_specimen-digitization-database_public';
  reader_role constant text := 'firebasereader_specimen-digitization-database_public';
  initializer constant text := 'specimen-data-initialize@specimen-digitization.iam';
  actor text;
  relation record;
BEGIN
  IF current_database() <> 'specimen-digitization-database' THEN
    RAISE EXCEPTION 'wrong initialized database';
  END IF;
  IF (SELECT count(*) FROM pg_roles WHERE rolname IN (owner_role,writer_role,reader_role)
      AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
      AND NOT rolreplication AND NOT rolbypassrls) <> 3 THEN
    RAISE EXCEPTION 'application role attributes are not narrow';
  END IF;
  IF (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public') <> owner_role
     OR has_database_privilege(owner_role,current_database(),'CREATE') THEN
    RAISE EXCEPTION 'schema ownership or temporary database CREATE cleanup failed';
  END IF;
  FOREACH actor IN ARRAY ARRAY[owner_role,writer_role,reader_role,
      'specimen-data-release@specimen-digitization.iam',
      'service-716045864126@gcp-sa-firebasedataconnect.iam'] LOOP
    IF pg_has_role(actor,'cloudsqlsuperuser','MEMBER')
       OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=actor
         AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)) THEN
      RAISE EXCEPTION 'ordinary principal retains global SQL privilege';
    END IF;
  END LOOP;
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN (
      'specimen-api-runtime@specimen-digitization.iam',
      'specimen-worker-runtime@specimen-digitization.iam')) THEN
    RAISE EXCEPTION 'application runtime SQL identity is outside this initial release scope';
  END IF;
  IF NOT pg_has_role('specimen-data-release@specimen-digitization.iam',owner_role,'SET')
     OR NOT pg_has_role('service-716045864126@gcp-sa-firebasedataconnect.iam',writer_role,'USAGE')
     OR pg_has_role('service-716045864126@gcp-sa-firebasedataconnect.iam',owner_role,'MEMBER') THEN
    RAISE EXCEPTION 'ordinary role assignments differ';
  END IF;
  -- The IAM authentication marker survives assigned-role replacement. Verify
  -- its exact inert graph; never erase it to manufacture zero memberships.
  IF (SELECT count(*) FROM pg_roles WHERE rolname='cloudsqliamserviceaccount'
      AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb
      AND NOT rolreplication AND NOT rolbypassrls AND rolinherit
      AND rolconfig IS NULL AND rolconnlimit=-1 AND rolvaliduntil IS NULL) <> 1
     OR EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles u ON u.oid=m.member
       WHERE u.rolname='cloudsqliamserviceaccount') THEN
    RAISE EXCEPTION 'IAM authentication marker role is missing, elevated or inherits another role';
  END IF;
  IF EXISTS(
    WITH expected(member) AS (VALUES ('specimen-data-release@specimen-digitization.iam'::text),
      ('service-716045864126@gcp-sa-firebasedataconnect.iam'::text)),
    actual AS (SELECT u.rolname::text AS member,g.rolname::text AS grantor,
      m.admin_option,m.inherit_option,m.set_option
      FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
      JOIN pg_roles u ON u.oid=m.member JOIN pg_roles g ON g.oid=m.grantor
      WHERE r.rolname='cloudsqliamserviceaccount' AND u.rolname IN (SELECT member FROM expected)),
    approved AS (SELECT member,'cloudsqladmin'::text AS grantor,false AS admin_option,
      true AS inherit_option,true AS set_option FROM expected)
    (SELECT * FROM actual EXCEPT SELECT * FROM approved) UNION ALL
    (SELECT * FROM approved EXCEPT SELECT * FROM actual)) THEN
    RAISE EXCEPTION 'ordinary IAM authentication marker grant or options differ';
  END IF;
  IF EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
    JOIN pg_roles u ON u.oid=m.member WHERE
      u.rolname IN (owner_role,writer_role,reader_role)
      OR (u.rolname='specimen-data-release@specimen-digitization.iam'
          AND (r.rolname NOT IN (owner_role,'cloudsqliamserviceaccount') OR m.admin_option OR NOT m.set_option OR NOT m.inherit_option))
      OR (u.rolname='service-716045864126@gcp-sa-firebasedataconnect.iam'
          AND (r.rolname NOT IN (writer_role,'cloudsqliamserviceaccount') OR m.admin_option OR NOT m.set_option OR NOT m.inherit_option))) THEN
    RAISE EXCEPTION 'unapproved effective membership path or membership options';
  END IF;
  IF EXISTS(
    WITH app_roles(role_name) AS (VALUES (owner_role),(writer_role),(reader_role)),
    actual AS (SELECT r.rolname::text AS role_name,u.rolname::text AS member,
        g.rolname::text AS grantor,m.admin_option,m.inherit_option,m.set_option
      FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
      JOIN pg_roles u ON u.oid=m.member JOIN pg_roles g ON g.oid=m.grantor
      WHERE r.rolname IN (owner_role,writer_role,reader_role)),
    expected(role_name,member,grantor,admin_option,inherit_option,set_option) AS (
      -- PostgreSQL18 creates an automatic ADMIN-only membership through its
      -- bootstrap superuser (reserved OID 10); resolve its actual catalog name.
      SELECT role_name,'cloudsqlsuperuser',pg_get_userbyid(10)::text,true,false,false FROM app_roles
      UNION ALL SELECT role_name,'cloudsqlsuperuser','cloudsqlsuperuser',false,true,true FROM app_roles
      UNION ALL SELECT owner_role,'specimen-data-release@specimen-digitization.iam','cloudsqlsuperuser',false,true,true
      UNION ALL SELECT writer_role,'service-716045864126@gcp-sa-firebasedataconnect.iam','cloudsqlsuperuser',false,true,true)
    (SELECT * FROM actual EXCEPT SELECT * FROM expected) UNION ALL
    (SELECT * FROM expected EXCEPT SELECT * FROM actual)) THEN
    RAISE EXCEPTION 'complete application role recipients, grantors or membership options differ';
  END IF;
  IF (SELECT count(*) FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace,
      LATERAL aclexplode(d.defaclacl) a
      WHERE n.nspname='public' AND pg_get_userbyid(d.defaclrole)=owner_role
        AND pg_get_userbyid(a.grantee)=writer_role AND NOT a.is_grantable
        AND ((d.defaclobjtype='r' AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE'))
          OR (d.defaclobjtype='S' AND a.privilege_type='USAGE'))) <> 5
     OR EXISTS(SELECT 1 FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace,
      LATERAL aclexplode(d.defaclacl) a WHERE n.nspname='public'
        AND pg_get_userbyid(a.grantee) IN (writer_role,reader_role)
        AND (a.is_grantable OR pg_get_userbyid(d.defaclrole)<>owner_role
          OR (pg_get_userbyid(a.grantee)=writer_role AND NOT
            ((d.defaclobjtype='r' AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE'))
              OR (d.defaclobjtype='S' AND a.privilege_type='USAGE')))
          OR (pg_get_userbyid(a.grantee)=reader_role AND NOT (d.defaclobjtype='r' AND a.privilege_type='SELECT')))) THEN
    RAISE EXCEPTION 'default privileges differ from the exact reviewed CRUD contract';
  END IF;
  IF EXISTS(SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid=d.refobjid
    WHERE d.refclassid='pg_authid'::regclass AND r.rolname=initializer) THEN
    RAISE EXCEPTION 'temporary initializer owns objects or grant dependencies';
  END IF;
  IF EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.grantor
      WHERE r.rolname=initializer) THEN
    RAISE EXCEPTION 'temporary initializer remains a role grantor';
  END IF;
  IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')
        AND pg_get_userbyid(c.relowner)<>owner_role)
     OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind IN ('r','p') AND
        (NOT has_table_privilege(writer_role,c.oid,'SELECT')
          OR NOT has_table_privilege(writer_role,c.oid,'INSERT')
          OR NOT has_table_privilege(writer_role,c.oid,'UPDATE')
          OR NOT has_table_privilege(writer_role,c.oid,'DELETE')
          OR has_table_privilege(writer_role,c.oid,'TRUNCATE')
          OR NOT has_table_privilege(reader_role,c.oid,'SELECT'))) THEN
    RAISE EXCEPTION 'schema DDL did not run as the reviewed owner or effective table privileges differ';
  END IF;
  IF EXISTS(
    WITH actual AS (SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee)::text END AS grantee,
        pg_get_userbyid(a.grantor)::text AS grantor,a.privilege_type,a.is_grantable
      FROM pg_namespace n,LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a WHERE n.nspname='public'),
    expected(grantee,grantor,privilege_type,is_grantable) AS (VALUES
      (owner_role,owner_role,'USAGE',false),(owner_role,owner_role,'CREATE',false),
      (writer_role,owner_role,'USAGE',false),(reader_role,owner_role,'USAGE',false))
    (SELECT * FROM actual EXCEPT SELECT * FROM expected) UNION ALL
    (SELECT * FROM expected EXCEPT SELECT * FROM actual)) THEN
    RAISE EXCEPTION 'complete public schema ACL differs';
  END IF;
  IF EXISTS(
    WITH actual AS (SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee)::text END AS grantee,
        pg_get_userbyid(a.grantor)::text AS grantor,a.privilege_type,a.is_grantable
      FROM pg_database d,LATERAL aclexplode(COALESCE(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=current_database()),
    expected(grantee,grantor,privilege_type,is_grantable) AS (VALUES
      ('cloudsqlsuperuser','cloudsqlsuperuser','CREATE',false),
      ('cloudsqlsuperuser','cloudsqlsuperuser','CONNECT',false),
      ('cloudsqlsuperuser','cloudsqlsuperuser','TEMPORARY',false),
      (owner_role,'cloudsqlsuperuser','CONNECT',false),(writer_role,'cloudsqlsuperuser','CONNECT',false),
      (reader_role,'cloudsqlsuperuser','CONNECT',false))
    (SELECT * FROM actual EXCEPT SELECT * FROM expected) UNION ALL
    (SELECT * FROM expected EXCEPT SELECT * FROM actual)) THEN
    RAISE EXCEPTION 'complete database ACL differs';
  END IF;
  IF EXISTS(
    WITH actual AS (SELECT pg_get_userbyid(d.defaclrole)::text AS owner,
        COALESCE(n.nspname::text,'GLOBAL') AS namespace,d.defaclobjtype::text AS kind,
        CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee)::text END AS grantee,
        pg_get_userbyid(a.grantor)::text AS grantor,a.privilege_type,a.is_grantable
      FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace,
      LATERAL aclexplode(d.defaclacl) a),
    expected(owner,namespace,kind,grantee,grantor,privilege_type,is_grantable) AS (VALUES
      (owner_role,'public','r',writer_role,owner_role,'SELECT',false),
      (owner_role,'public','r',writer_role,owner_role,'INSERT',false),
      (owner_role,'public','r',writer_role,owner_role,'UPDATE',false),
      (owner_role,'public','r',writer_role,owner_role,'DELETE',false),
      (owner_role,'public','r',reader_role,owner_role,'SELECT',false),
      (owner_role,'public','S',writer_role,owner_role,'USAGE',false))
    (SELECT * FROM actual EXCEPT SELECT * FROM expected) UNION ALL
    (SELECT * FROM expected EXCEPT SELECT * FROM actual)) THEN
    RAISE EXCEPTION 'complete default ACL set differs including global or PUBLIC grants';
  END IF;
  FOR relation IN SELECT c.* FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f','S') LOOP
    IF EXISTS(
      WITH actual AS (SELECT a.grantee,a.grantor,a.privilege_type,a.is_grantable
        FROM aclexplode(COALESCE(relation.relacl,acldefault(CASE WHEN relation.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,relation.relowner))) a),
      expected AS (SELECT a.grantee,a.grantor,a.privilege_type,a.is_grantable
        FROM aclexplode(acldefault(CASE WHEN relation.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,relation.relowner)) a
        WHERE a.grantee=relation.relowner
        UNION ALL SELECT r.oid,relation.relowner,p.privilege,false FROM pg_roles r,
          LATERAL unnest(CASE WHEN relation.relkind='S' THEN ARRAY['USAGE']
            ELSE ARRAY['SELECT','INSERT','UPDATE','DELETE'] END) p(privilege) WHERE r.rolname=writer_role
        UNION ALL SELECT r.oid,relation.relowner,'SELECT',false FROM pg_roles r
          WHERE r.rolname=reader_role AND relation.relkind<>'S')
      (SELECT * FROM actual EXCEPT SELECT * FROM expected) UNION ALL
      (SELECT * FROM expected EXCEPT SELECT * FROM actual))
      OR EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=relation.oid AND attacl IS NOT NULL) THEN
      RAISE EXCEPTION 'complete relation or column privilege set differs';
    END IF;
  END LOOP;
END
$postconditions$;
SELECT jsonb_build_object('database',current_database(),
  'database_properties',(SELECT jsonb_build_object('encoding',encoding,'collation',datcollate,
    'ctype',datctype,'locale_provider',datlocprovider,'locale',datlocale,'collation_version',datcollversion)
    FROM pg_database WHERE datname=current_database()),
  'database_oid',(SELECT oid::text FROM pg_database WHERE datname=current_database()),
  'database_owner',(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()),
  'schema_owner',(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'),
  'default_privileges',(SELECT jsonb_agg(jsonb_build_object('role',pg_get_userbyid(defaclrole),
    'namespace',n.nspname,'type',defaclobjtype,'acl',defaclacl::text) ORDER BY defaclobjtype)
    FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname='public'),
  'roles_narrow',true,'initializer_dependencies',false) AS postconditions;
