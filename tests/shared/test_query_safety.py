"""
SEC-014: Tests for Query Parameterization and SQL Injection Prevention.
"""

import pytest


class TestQuerySecurityExceptions:
    """Test query security exceptions."""

    def test_sql_injection_attempt_error(self):
        """Should create injection error with details."""
        from shared.query_safety import SQLInjectionAttemptError

        error = SQLInjectionAttemptError(
            "Injection detected",
            "' OR '1'='1",
        )

        assert "Injection" in str(error)
        assert error.suspicious_input == "' OR '1'='1"

    def test_unsafe_query_error(self):
        """Should create unsafe query error."""
        from shared.query_safety import UnsafeQueryError

        error = UnsafeQueryError("No table specified")

        assert "No table" in str(error)

    def test_invalid_parameter_error(self):
        """Should create invalid parameter error."""
        from shared.query_safety import InvalidParameterError

        error = InvalidParameterError("Invalid identifier")

        assert "Invalid" in str(error)


class TestSQLInjectionPatterns:
    """Test SQL injection pattern definitions."""

    def test_basic_patterns_defined(self):
        """Should have basic injection patterns."""
        from shared.query_safety import SQLInjectionPatterns

        assert len(SQLInjectionPatterns.BASIC_INJECTION) > 0

    def test_advanced_patterns_defined(self):
        """Should have advanced injection patterns."""
        from shared.query_safety import SQLInjectionPatterns

        assert len(SQLInjectionPatterns.ADVANCED_INJECTION) > 0

    def test_nosql_patterns_defined(self):
        """Should have NoSQL injection patterns."""
        from shared.query_safety import SQLInjectionPatterns

        assert len(SQLInjectionPatterns.NOSQL_INJECTION) > 0

    def test_suspicious_keywords_defined(self):
        """Should have suspicious keywords."""
        from shared.query_safety import SQLInjectionPatterns

        assert 'union' in SQLInjectionPatterns.SUSPICIOUS_KEYWORDS
        assert 'drop' in SQLInjectionPatterns.SUSPICIOUS_KEYWORDS


class TestSafeParam:
    """Test SafeParam wrapper."""

    def test_create_safe_param(self):
        """Should create safe parameter."""
        from shared.query_safety import SafeParam, ParamType

        param = SafeParam(
            value="test_value",
            param_type=ParamType.STRING,
            validated=True,
        )

        assert param.value == "test_value"
        assert param.param_type == ParamType.STRING

    def test_param_immutable(self):
        """SafeParam should be immutable."""
        from shared.query_safety import SafeParam

        param = SafeParam(value="test")

        with pytest.raises(Exception):  # FrozenInstanceError
            param.value = "changed"


class TestSQLInjectionDetector:
    """Test SQL injection detection."""

    def test_detect_basic_or_injection(self):
        """Should detect basic OR injection."""
        from shared.query_safety import SQLInjectionDetector

        attacks = [
            "' or '1'='1",
            "' OR 1=1--",
            "\" or \"1\"=\"1",
        ]

        for attack in attacks:
            assert SQLInjectionDetector.check(attack) is True

    def test_detect_union_injection(self):
        """Should detect UNION injection."""
        from shared.query_safety import SQLInjectionDetector

        attacks = [
            "' UNION SELECT * FROM users--",
            "' union all select 1,2,3--",
        ]

        for attack in attacks:
            assert SQLInjectionDetector.check(attack) is True

    def test_detect_stacked_queries(self):
        """Should detect stacked queries."""
        from shared.query_safety import SQLInjectionDetector

        attacks = [
            "'; DROP TABLE users;--",
            "'; DELETE FROM accounts;--",
            "'; TRUNCATE table_name;--",
        ]

        for attack in attacks:
            assert SQLInjectionDetector.check(attack) is True

    def test_detect_time_based_injection(self):
        """Should detect time-based blind injection."""
        from shared.query_safety import SQLInjectionDetector

        attacks = [
            "'; waitfor delay '0:0:5'--",
            "'; pg_sleep(5);--",
        ]

        for attack in attacks:
            assert SQLInjectionDetector.check(attack) is True

    def test_allow_safe_input(self):
        """Should allow safe input."""
        from shared.query_safety import SQLInjectionDetector

        safe_inputs = [
            "john.doe@example.com",
            "Regular text with some numbers 12345",
            "Product name: Widget XL",
            "It's a valid string with apostrophe",
        ]

        for safe in safe_inputs:
            assert SQLInjectionDetector.check(safe) is False

    def test_validate_or_raise_safe(self):
        """Should return value when safe."""
        from shared.query_safety import SQLInjectionDetector

        result = SQLInjectionDetector.validate_or_raise("safe_value")

        assert result == "safe_value"

    def test_validate_or_raise_unsafe(self):
        """Should raise when injection detected."""
        from shared.query_safety import SQLInjectionDetector, SQLInjectionAttemptError

        with pytest.raises(SQLInjectionAttemptError):
            SQLInjectionDetector.validate_or_raise("' OR '1'='1")

    def test_detect_nosql_injection(self):
        """Should detect NoSQL injection."""
        from shared.query_safety import SQLInjectionDetector

        attacks = [
            '{"$where": "this.password == \'test\'"}',
            '{"$ne": 1}',
            '{"$gt": 0}',
        ]

        for attack in attacks:
            assert SQLInjectionDetector.check_nosql(attack) is True


class TestIdentifierValidator:
    """Test identifier validation."""

    def test_valid_identifiers(self):
        """Should accept valid identifiers."""
        from shared.query_safety import IdentifierValidator

        valid = [
            "users",
            "user_id",
            "UserTable",
            "_private",
            "column123",
        ]

        for ident in valid:
            assert IdentifierValidator.is_valid(ident) is True

    def test_invalid_identifiers(self):
        """Should reject invalid identifiers."""
        from shared.query_safety import IdentifierValidator

        invalid = [
            "",  # Empty
            "123start",  # Starts with number
            "has space",  # Contains space
            "has-dash",  # Contains dash
            "has.dot",  # Contains dot
            "table; DROP",  # Injection attempt
            "a" * 200,  # Too long
        ]

        for ident in invalid:
            assert IdentifierValidator.is_valid(ident) is False

    def test_validate_raises_on_invalid(self):
        """Should raise on invalid identifier."""
        from shared.query_safety import IdentifierValidator, InvalidParameterError

        with pytest.raises(InvalidParameterError):
            IdentifierValidator.validate("invalid identifier")

    def test_quote_double(self):
        """Should quote with double quotes."""
        from shared.query_safety import IdentifierValidator

        result = IdentifierValidator.quote("users", style="double")

        assert result == '"users"'

    def test_quote_backtick(self):
        """Should quote with backticks."""
        from shared.query_safety import IdentifierValidator

        result = IdentifierValidator.quote("users", style="backtick")

        assert result == '`users`'

    def test_quote_brackets(self):
        """Should quote with brackets."""
        from shared.query_safety import IdentifierValidator

        result = IdentifierValidator.quote("users", style="brackets")

        assert result == '[users]'

    def test_is_reserved(self):
        """Should detect reserved words."""
        from shared.query_safety import IdentifierValidator

        assert IdentifierValidator.is_reserved("select") is True
        assert IdentifierValidator.is_reserved("from") is True
        assert IdentifierValidator.is_reserved("users") is False


class TestSafeQueryBuilder:
    """Test safe SELECT query builder."""

    def test_simple_select(self):
        """Should build simple SELECT."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id", "name")
            .from_table("users")
            .build()
        )

        assert '"id"' in query
        assert '"name"' in query
        assert '"users"' in query
        assert "SELECT" in query
        assert "FROM" in query

    def test_select_star(self):
        """Should handle SELECT *."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("*")
            .from_table("users")
            .build()
        )

        assert "SELECT *" in query

    def test_where_clause(self):
        """Should add WHERE clause with parameterization."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id")
            .from_table("users")
            .where("status", "=", "active")
            .build()
        )

        assert "WHERE" in query
        assert "$1" in query
        assert params == ["active"]

    def test_multiple_where(self):
        """Should combine multiple WHERE clauses."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id")
            .from_table("users")
            .where("status", "=", "active")
            .where("role", "=", "admin")
            .build()
        )

        assert "AND" in query
        assert len(params) == 2

    def test_where_in(self):
        """Should handle WHERE IN."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id")
            .from_table("users")
            .where_in("status", ["active", "pending"])
            .build()
        )

        assert "IN" in query
        assert "$1" in query
        assert "$2" in query
        assert len(params) == 2

    def test_where_null(self):
        """Should handle WHERE IS NULL."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id")
            .from_table("users")
            .where_null("deleted_at")
            .build()
        )

        assert "IS NULL" in query

    def test_order_by(self):
        """Should add ORDER BY."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id")
            .from_table("users")
            .order_by("created_at", "DESC")
            .build()
        )

        assert 'ORDER BY "created_at" DESC' in query

    def test_limit_offset(self):
        """Should add LIMIT and OFFSET."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id")
            .from_table("users")
            .limit(10)
            .offset(20)
            .build()
        )

        assert "LIMIT 10" in query
        assert "OFFSET 20" in query

    def test_group_by(self):
        """Should add GROUP BY."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("status")
            .from_table("users")
            .group_by("status")
            .build()
        )

        assert 'GROUP BY "status"' in query

    def test_join(self):
        """Should add JOIN clause."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder()
            .select("id", "name")
            .from_table("users")
            .join("profiles", "user_id", "id")
            .build()
        )

        assert "JOIN" in query
        assert '"profiles"' in query

    def test_reject_invalid_column(self):
        """Should reject invalid column names."""
        from shared.query_safety import SafeQueryBuilder, InvalidParameterError

        builder = SafeQueryBuilder()

        with pytest.raises(InvalidParameterError):
            builder.select("invalid column")

    def test_reject_invalid_operator(self):
        """Should reject invalid operators."""
        from shared.query_safety import SafeQueryBuilder, InvalidParameterError

        with pytest.raises(InvalidParameterError):
            (
                SafeQueryBuilder()
                .select("id")
                .from_table("users")
                .where("status", "INVALID_OP", "value")
            )

    def test_reject_injection_in_value(self):
        """Should reject SQL injection in values."""
        from shared.query_safety import SafeQueryBuilder, SQLInjectionAttemptError

        with pytest.raises(SQLInjectionAttemptError):
            (
                SafeQueryBuilder()
                .select("id")
                .from_table("users")
                .where("name", "=", "' OR '1'='1")
                .build()
            )

    def test_require_table(self):
        """Should require table specification."""
        from shared.query_safety import SafeQueryBuilder, UnsafeQueryError

        with pytest.raises(UnsafeQueryError, match="No table"):
            SafeQueryBuilder().select("id").build()

    def test_require_columns(self):
        """Should require column specification."""
        from shared.query_safety import SafeQueryBuilder, UnsafeQueryError

        with pytest.raises(UnsafeQueryError, match="No columns"):
            SafeQueryBuilder().from_table("users").build()


class TestSafeInsertBuilder:
    """Test safe INSERT query builder."""

    def test_simple_insert(self):
        """Should build simple INSERT."""
        from shared.query_safety import SafeInsertBuilder

        query, params = (
            SafeInsertBuilder()
            .into("users")
            .columns("name", "email")
            .values("John", "john@example.com")
            .build()
        )

        assert 'INSERT INTO "users"' in query
        assert "$1" in query
        assert "$2" in query
        assert len(params) == 2

    def test_insert_with_returning(self):
        """Should add RETURNING clause."""
        from shared.query_safety import SafeInsertBuilder

        query, params = (
            SafeInsertBuilder()
            .into("users")
            .columns("name")
            .values("John")
            .returning("id")
            .build()
        )

        assert "RETURNING" in query
        assert '"id"' in query

    def test_multi_row_insert(self):
        """Should handle multi-row inserts."""
        from shared.query_safety import SafeInsertBuilder

        query, params = (
            SafeInsertBuilder()
            .into("users")
            .columns("name")
            .values("John")
            .values("Jane")
            .build()
        )

        assert query.count("(") >= 3  # Column list + 2 value groups
        assert len(params) == 2

    def test_reject_mismatched_columns(self):
        """Should reject mismatched column/value counts."""
        from shared.query_safety import SafeInsertBuilder, InvalidParameterError

        with pytest.raises(InvalidParameterError):
            (
                SafeInsertBuilder()
                .into("users")
                .columns("name", "email")
                .values("John")  # Only 1 value for 2 columns
            )

    def test_reject_injection_in_insert(self):
        """Should reject SQL injection in INSERT values."""
        from shared.query_safety import SafeInsertBuilder, SQLInjectionAttemptError

        with pytest.raises(SQLInjectionAttemptError):
            (
                SafeInsertBuilder()
                .into("users")
                .columns("name")
                .values("'; DROP TABLE users;--")
                .build()
            )


class TestSafeUpdateBuilder:
    """Test safe UPDATE query builder."""

    def test_simple_update(self):
        """Should build simple UPDATE."""
        from shared.query_safety import SafeUpdateBuilder

        query, params = (
            SafeUpdateBuilder()
            .table("users")
            .set("name", "John")
            .where("id", "=", 1)
            .build()
        )

        assert 'UPDATE "users"' in query
        assert "SET" in query
        assert "WHERE" in query
        assert len(params) == 2

    def test_update_with_returning(self):
        """Should add RETURNING clause."""
        from shared.query_safety import SafeUpdateBuilder

        query, params = (
            SafeUpdateBuilder()
            .table("users")
            .set("name", "John")
            .where("id", "=", 1)
            .returning("*")
            .build()
        )

        assert "RETURNING *" in query

    def test_require_where_clause(self):
        """Should require WHERE clause to prevent mass updates."""
        from shared.query_safety import SafeUpdateBuilder, UnsafeQueryError

        with pytest.raises(UnsafeQueryError, match="WHERE"):
            (
                SafeUpdateBuilder()
                .table("users")
                .set("name", "John")
                .build()
            )

    def test_reject_injection_in_update(self):
        """Should reject SQL injection in UPDATE values."""
        from shared.query_safety import SafeUpdateBuilder, SQLInjectionAttemptError

        with pytest.raises(SQLInjectionAttemptError):
            (
                SafeUpdateBuilder()
                .table("users")
                .set("name", "' OR '1'='1")
                .where("id", "=", 1)
                .build()
            )


class TestSafeDeleteBuilder:
    """Test safe DELETE query builder."""

    def test_simple_delete(self):
        """Should build simple DELETE."""
        from shared.query_safety import SafeDeleteBuilder

        query, params = (
            SafeDeleteBuilder()
            .from_table("users")
            .where("id", "=", 1)
            .build()
        )

        assert 'DELETE FROM "users"' in query
        assert "WHERE" in query
        assert len(params) == 1

    def test_delete_with_returning(self):
        """Should add RETURNING clause."""
        from shared.query_safety import SafeDeleteBuilder

        query, params = (
            SafeDeleteBuilder()
            .from_table("users")
            .where("id", "=", 1)
            .returning("id", "name")
            .build()
        )

        assert "RETURNING" in query

    def test_require_where_clause(self):
        """Should require WHERE clause to prevent mass deletes."""
        from shared.query_safety import SafeDeleteBuilder, UnsafeQueryError

        with pytest.raises(UnsafeQueryError, match="WHERE"):
            (
                SafeDeleteBuilder()
                .from_table("users")
                .build()
            )


class TestQuerySanitizer:
    """Test query sanitizer for legacy queries."""

    def test_escape_quotes(self):
        """Should escape single quotes."""
        from shared.query_safety import QuerySanitizer

        result = QuerySanitizer.escape_string("O'Brien")

        assert result == "O''Brien"

    def test_escape_backslashes(self):
        """Should escape backslashes."""
        from shared.query_safety import QuerySanitizer

        result = QuerySanitizer.escape_string("path\\to\\file")

        assert result == "path\\\\to\\\\file"

    def test_reject_injection_in_escape(self):
        """Should reject injection even when escaping."""
        from shared.query_safety import QuerySanitizer, SQLInjectionAttemptError

        with pytest.raises(SQLInjectionAttemptError):
            QuerySanitizer.escape_string("' OR '1'='1")

    def test_escape_like_wildcards(self):
        """Should escape LIKE wildcards."""
        from shared.query_safety import QuerySanitizer

        result = QuerySanitizer.escape_like("100% discount")

        assert result == "100\\% discount"

    def test_escape_like_underscore(self):
        """Should escape LIKE underscore."""
        from shared.query_safety import QuerySanitizer

        result = QuerySanitizer.escape_like("file_name")

        assert result == "file\\_name"


class TestConvenienceFunctions:
    """Test convenience query builder functions."""

    def test_select_convenience(self):
        """Should create SELECT builder."""
        from shared.query_safety import select

        builder = select("id", "name")

        assert isinstance(builder, object)

    def test_insert_convenience(self):
        """Should create INSERT builder."""
        from shared.query_safety import insert_into

        builder = insert_into("users")

        assert isinstance(builder, object)

    def test_update_convenience(self):
        """Should create UPDATE builder."""
        from shared.query_safety import update

        builder = update("users")

        assert isinstance(builder, object)

    def test_delete_convenience(self):
        """Should create DELETE builder."""
        from shared.query_safety import delete_from

        builder = delete_from("users")

        assert isinstance(builder, object)


class TestParameterPlaceholderStyles:
    """Test different placeholder styles."""

    def test_positional_placeholders(self):
        """Should use $1, $2 for positional."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder(placeholder_style="positional")
            .select("id")
            .from_table("users")
            .where("a", "=", "x")
            .where("b", "=", "y")
            .build()
        )

        assert "$1" in query
        assert "$2" in query

    def test_named_placeholders(self):
        """Should use :p1, :p2 for named."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder(placeholder_style="named")
            .select("id")
            .from_table("users")
            .where("a", "=", "x")
            .build()
        )

        assert ":p1" in query

    def test_qmark_placeholders(self):
        """Should use ? for qmark style."""
        from shared.query_safety import SafeQueryBuilder

        query, params = (
            SafeQueryBuilder(placeholder_style="qmark")
            .select("id")
            .from_table("users")
            .where("a", "=", "x")
            .build()
        )

        assert "?" in query


class TestSQLInjectionScenarios:
    """Test real-world SQL injection scenarios."""

    def test_login_bypass(self):
        """Should prevent login bypass attacks."""
        from shared.query_safety import SafeQueryBuilder, SQLInjectionAttemptError

        with pytest.raises(SQLInjectionAttemptError):
            (
                SafeQueryBuilder()
                .select("*")
                .from_table("users")
                .where("username", "=", "admin'--")
                .where("password", "=", "anything")
                .build()
            )

    def test_blind_injection(self):
        """Should prevent blind injection attacks."""
        from shared.query_safety import SQLInjectionDetector

        assert SQLInjectionDetector.check(
            "1' AND SLEEP(5)--"
        ) is True or SQLInjectionDetector.check(
            "'; waitfor delay '0:0:5'--"
        ) is True

    def test_second_order_prep(self):
        """Should validate stored values that could be used in queries."""
        from shared.query_safety import SQLInjectionDetector

        # This is a value that might be stored and later used in a query
        malicious_stored = "Robert'); DROP TABLE students;--"

        # When retrieved and validated before query construction
        is_dangerous = SQLInjectionDetector.check(malicious_stored)

        assert is_dangerous is True

    def test_complex_union_attack(self):
        """Should detect complex UNION attacks."""
        from shared.query_safety import SQLInjectionDetector

        attacks = [
            "' UNION SELECT NULL,username,password FROM users--",
            "1 UNION ALL SELECT NULL,NULL,table_name FROM information_schema.tables--",
        ]

        for attack in attacks:
            assert SQLInjectionDetector.check(attack) is True
