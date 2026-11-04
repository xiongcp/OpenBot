-- Authority bytes are added without manufacturing bindings for existing operations.
ALTER TABLE operations ADD COLUMN proposal_canonical_json TEXT;
CREATE TRIGGER operation_canonical_required BEFORE INSERT ON operations
WHEN NEW.proposal_canonical_json IS NULL OR CASE WHEN json_valid(NEW.proposal_canonical_json)
    THEN json_type(NEW.proposal_canonical_json) <> 'object' ELSE 1 END
BEGIN SELECT RAISE(ABORT, 'new operations require authoritative proposal bytes'); END;
CREATE TRIGGER operation_canonical_immutable BEFORE UPDATE ON operations
WHEN NEW.proposal_canonical_json IS NOT OLD.proposal_canonical_json
BEGIN SELECT RAISE(ABORT, 'authoritative proposal bytes are immutable'); END;
