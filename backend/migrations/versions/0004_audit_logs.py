"""audit_logs: thêm vai trò người thực hiện, đối tượng có cấu trúc, ip_hash, request_id; chỉ thêm (trigger chặn sửa/xóa) (T-013 phần còn lại)

Bảng chưa từng được ghi nên bỏ cột `target` (chuỗi tự do) để thay bằng target_type/target_id.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.execute("""
        ALTER TABLE audit_logs
          DROP COLUMN target,
          ADD COLUMN actor_role text NOT NULL DEFAULT 'system'
            CHECK (actor_role IN ('user','staff','admin','agent','system')),
          ADD COLUMN target_type text,
          ADD COLUMN target_id text,
          ADD COLUMN ip_hash text,
          ADD COLUMN request_id text,
          ADD CONSTRAINT audit_logs_action_format CHECK (action ~ '^[a-z][a-z_]*\\.[a-z][a-z_]*$'),
          ADD CONSTRAINT audit_logs_detail_object CHECK (detail IS NULL OR jsonb_typeof(detail) = 'object')""")
    op.execute("CREATE INDEX audit_logs_at_idx ON audit_logs(at)")
    op.execute("CREATE INDEX audit_logs_actor_idx ON audit_logs(actor_id, at)")
    op.execute("CREATE INDEX audit_logs_target_idx ON audit_logs(target_type, target_id)")
    op.execute("""
        CREATE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'audit_logs chỉ được thêm, không sửa/xóa'; END; $$ LANGUAGE plpgsql""")
    op.execute("""
        CREATE TRIGGER audit_logs_no_change BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()""")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_change ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")
    op.execute("DROP INDEX IF EXISTS audit_logs_target_idx")
    op.execute("DROP INDEX IF EXISTS audit_logs_actor_idx")
    op.execute("DROP INDEX IF EXISTS audit_logs_at_idx")
    op.execute("""
        ALTER TABLE audit_logs
          DROP CONSTRAINT audit_logs_detail_object,
          DROP CONSTRAINT audit_logs_action_format,
          DROP COLUMN request_id, DROP COLUMN ip_hash, DROP COLUMN target_id,
          DROP COLUMN target_type, DROP COLUMN actor_role,
          ADD COLUMN target text""")
