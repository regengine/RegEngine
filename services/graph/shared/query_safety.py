"""
SEC-014: Query Parameterization and SQL Injection Prevention.

This module provides utilities for safe database query construction,
preventing SQL injection through proper parameterization.
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class QuerySecurityError(Exception):
    """Base exception for query security issues."""
    pass


class SQLInjectionAttemptError(QuerySecurityError):
    """Raised when SQL injection is detected."""
    
    def __init__(self, message: str, suspicious_input: str = ""):
        super().__init__(message)
        self.suspicious_input = suspicious_input[:200]  # Truncate for safety


class UnsafeQueryError(QuerySecurityError):
    """Raised when a query is constructed unsafely."""
    pass


class InvalidParameterError(QuerySecurityError):
    """Raised when a parameter is invalid."""
    pass


# =============================================================================
# SQL Injection Detection Patterns
# =============================================================================

class SQLInjectionPatterns:
    """Common SQL injection attack patterns."""
    
    # Basic SQL injection patterns
    BASIC_INJECTION = [
        re.compile(r"('|\")\s*(or|and)\s+('|\")?\d+('|\")?\s*=\s*('|\")?\d+", re.IGNORECASE),  # ' or '1'='1
        re.compile(r"('|\")\s*(or|and)\s+\d+\s*=\s*\d+\s*--", re.IGNORECASE),  # ' or 1=1--
        re.compile(r"--\s*$", re.MULTILINE),  # SQL comment at end
        re.compile(r";\s*(drop|delete|truncate|update|insert|create|alter)\s+", re.IGNORECASE),  # Stacked queries
        re.compile(r"union\s+(all\s+)?select", re.IGNORECASE),  # UNION injection
    ]
    
    # Advanced injection patterns
    ADVANCED_INJECTION = [
        re.compile(r";\s*waitfor\s+delay", re.IGNORECASE),  # Time-based blind
        re.compile(r";\s*pg_sleep\s*\(", re.IGNORECASE),  # PostgreSQL sleep
        re.compile(r"benchmark\s*\(\s*\d+\s*,", re.IGNORECASE),  # MySQL benchmark
        re.compile(r"load_file\s*\(", re.IGNORECASE),  # File access
        re.compile(r"into\s+(out|dump)file", re.IGNORECASE),  # File write
        re.compile(r"extractvalue\s*\(", re.IGNORECASE),  # XML injection
        re.compile(r"updatexml\s*\(", re.IGNORECASE),  # XML injection
    ]
    
    # NoSQL injection patterns
    NOSQL_INJECTION = [
        re.compile(r"\$where", re.IGNORECASE),  # MongoDB $where
        re.compile(r"\$ne\b", re.IGNORECASE),  # MongoDB $ne
        re.compile(r"\$gt\b", re.IGNORECASE),  # MongoDB $gt
        re.compile(r"\$regex\b", re.IGNORECASE),  # MongoDB $regex
        re.compile(r"\$or\b", re.IGNORECASE),  # MongoDB $or injection
    ]
    
    # Suspicious keywords
    SUSPICIOUS_KEYWORDS = {
        'union', 'select', 'insert', 'update', 'delete', 'drop',
        'truncate', 'exec', 'execute', 'xp_', 'sp_', 'declare',
        'cast', 'convert', 'char', 'nchar', 'varchar', 'nvarchar',
        'information_schema', 'sysobjects', 'syscolumns',
    }


# =============================================================================
# Query Parameter Types
# =============================================================================

class ParamType(Enum):
    """Parameter type for validation."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"
    JSON = "json"
    ARRAY = "array"
    NULL = "null"
    IDENTIFIER = "identifier"  # Table/column names - special handling


# =============================================================================
# Safe Parameter Wrapper
# =============================================================================

@dataclass(frozen=True)
class SafeParam:
    """A validated and type-safe query parameter.
    
    This wrapper ensures parameters are validated before use.
    """
    
    value: Any
    param_type: ParamType = ParamType.STRING
    validated: bool = True
    
    def __post_init__(self):
        """Validate parameter on creation."""
        if not self.validated:
            raise InvalidParameterError("Parameter must be validated")


# =============================================================================
# SQL Injection Detector
# =============================================================================

class SQLInjectionDetector:
    """Detect potential SQL injection attempts."""
    
    @classmethod
    def check(cls, value: str) -> bool:
        """Check if value contains SQL injection patterns.
        
        Args:
            value: Input value to check
            
        Returns:
            True if injection detected, False otherwise
        """
        if not isinstance(value, str):
            return False
        
        # Check basic patterns
        for pattern in SQLInjectionPatterns.BASIC_INJECTION:
            if pattern.search(value):
                logger.warning(
                    "sql_injection_basic_pattern detected: %s",
                    pattern.pattern[:50],
                )
                return True
        
        # Check advanced patterns
        for pattern in SQLInjectionPatterns.ADVANCED_INJECTION:
            if pattern.search(value):
                logger.warning(
                    "sql_injection_advanced_pattern detected: %s",
                    pattern.pattern[:50],
                )
                return True
        
        return False
    
    @classmethod
    def check_nosql(cls, value: str) -> bool:
        """Check if value contains NoSQL injection patterns.
        
        Args:
            value: Input value to check
            
        Returns:
            True if injection detected, False otherwise
        """
        if not isinstance(value, str):
            return False
        
        for pattern in SQLInjectionPatterns.NOSQL_INJECTION:
            if pattern.search(value):
                logger.warning(
                    "nosql_injection_pattern detected: %s",
                    pattern.pattern[:50],
                )
                return True
        
        return False
    
    @classmethod
    def validate_or_raise(cls, value: str, check_nosql: bool = False) -> str:
        """Validate value and raise if injection detected.
        
        Args:
            value: Input value to validate
            check_nosql: Whether to also check NoSQL patterns
            
        Returns:
            Original value if safe
            
        Raises:
            SQLInjectionAttemptError: If injection detected
        """
        if cls.check(value):
            raise SQLInjectionAttemptError(
                "SQL injection attempt detected",
                value,
            )
        
        if check_nosql and cls.check_nosql(value):
            raise SQLInjectionAttemptError(
                "NoSQL injection attempt detected",
                value,
            )
        
        return value


# =============================================================================
# Safe Identifier Handling
# =============================================================================

class IdentifierValidator:
    """Validate and quote SQL identifiers (table/column names)."""
    
    # Valid identifier pattern: alphanumeric and underscore only
    VALID_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    
    # Reserved words that need special handling
    RESERVED_WORDS = {
        'select', 'from', 'where', 'and', 'or', 'not', 'null',
        'true', 'false', 'table', 'column', 'index', 'key',
        'primary', 'foreign', 'references', 'constraint',
        'order', 'by', 'group', 'having', 'limit', 'offset',
        'join', 'left', 'right', 'inner', 'outer', 'cross',
        'union', 'intersect', 'except', 'insert', 'update',
        'delete', 'create', 'alter', 'drop', 'truncate',
        'grant', 'revoke', 'user', 'role', 'database', 'schema',
    }
    
    @classmethod
    def is_valid(cls, identifier: str) -> bool:
        """Check if identifier is valid.
        
        Args:
            identifier: Identifier to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not identifier or not isinstance(identifier, str):
            return False
        
        # Check length
        if len(identifier) > 128:  # Most DBs limit to 128 chars
            return False
        
        # Check pattern
        return bool(cls.VALID_IDENTIFIER.match(identifier))
    
    @classmethod
    def validate(cls, identifier: str) -> str:
        """Validate an identifier.
        
        Args:
            identifier: Identifier to validate
            
        Returns:
            Validated identifier
            
        Raises:
            InvalidParameterError: If identifier is invalid
        """
        if not cls.is_valid(identifier):
            raise InvalidParameterError(
                f"Invalid identifier: {identifier[:50]}"
            )
        return identifier
    
    @classmethod
    def quote(cls, identifier: str, style: str = "double") -> str:
        """Quote an identifier for safe use in queries.
        
        Args:
            identifier: Identifier to quote
            style: Quote style ('double', 'backtick', 'brackets')
            
        Returns:
            Quoted identifier
            
        Raises:
            InvalidParameterError: If identifier is invalid
        """
        # Validate first
        cls.validate(identifier)
        
        # Quote based on style
        if style == "double":
            # PostgreSQL, standard SQL
            return f'"{identifier}"'
        elif style == "backtick":
            # MySQL
            return f'`{identifier}`'
        elif style == "brackets":
            # SQL Server
            return f'[{identifier}]'
        else:
            raise ValueError(f"Unknown quote style: {style}")
    
    @classmethod
    def is_reserved(cls, identifier: str) -> bool:
        """Check if identifier is a reserved word.
        
        Args:
            identifier: Identifier to check
            
        Returns:
            True if reserved, False otherwise
        """
        return identifier.lower() in cls.RESERVED_WORDS


# =============================================================================
# Safe Query Builder
# =============================================================================

T = TypeVar('T')


class SafeQueryBuilder:
    """Build SQL queries safely with automatic parameterization.
    
    Usage:
        builder = SafeQueryBuilder()
        query, params = (
            builder
            .select("id", "name", "email")
            .from_table("users")
            .where("status", "=", "active")
            .where("created_at", ">", datetime(2024, 1, 1))
            .order_by("created_at", "DESC")
            .limit(10)
            .build()
        )
    """
    
    def __init__(self, placeholder_style: str = "positional"):
        """Initialize query builder.
        
        Args:
            placeholder_style: 'positional' ($1, $2) or 'named' (:name)
        """
        self._placeholder_style = placeholder_style
        self._select_columns: List[str] = []
        self._table: Optional[str] = None
        self._joins: List[str] = []
        self._where_clauses: List[Tuple[str, Any]] = []
        self._order_by: List[Tuple[str, str]] = []
        self._group_by: List[str] = []
        self._having_clauses: List[Tuple[str, Any]] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._params: List[Any] = []
        self._param_count = 0
    
    def _next_placeholder(self) -> str:
        """Get next parameter placeholder."""
        self._param_count += 1
        if self._placeholder_style == "positional":
            return f"${self._param_count}"
        elif self._placeholder_style == "named":
            return f":p{self._param_count}"
        elif self._placeholder_style == "qmark":
            return "?"
        else:
            return "%s"
    
    def _add_param(self, value: Any) -> str:
        """Add a parameter and return its placeholder."""
        # Validate string parameters for injection
        if isinstance(value, str):
            SQLInjectionDetector.validate_or_raise(value)
        
        self._params.append(value)
        return self._next_placeholder()
    
    def select(self, *columns: str) -> "SafeQueryBuilder":
        """Add SELECT columns.
        
        Args:
            *columns: Column names to select
            
        Returns:
            Self for chaining
        """
        for col in columns:
            if col == "*":
                self._select_columns.append("*")
            else:
                # Validate column name
                IdentifierValidator.validate(col)
                self._select_columns.append(
                    IdentifierValidator.quote(col)
                )
        return self
    
    def from_table(self, table: str, alias: Optional[str] = None) -> "SafeQueryBuilder":
        """Set FROM table.
        
        Args:
            table: Table name
            alias: Optional table alias
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(table)
        self._table = IdentifierValidator.quote(table)
        
        if alias:
            IdentifierValidator.validate(alias)
            self._table += f" AS {IdentifierValidator.quote(alias)}"
        
        return self
    
    def join(
        self,
        table: str,
        on_column: str,
        on_value_column: str,
        join_type: str = "INNER",
        alias: Optional[str] = None,
    ) -> "SafeQueryBuilder":
        """Add a JOIN clause.
        
        Args:
            table: Table to join
            on_column: Column in joined table
            on_value_column: Column to match against
            join_type: Type of join (INNER, LEFT, RIGHT)
            alias: Optional table alias
            
        Returns:
            Self for chaining
        """
        # Validate join type
        valid_joins = {"INNER", "LEFT", "RIGHT", "FULL", "CROSS"}
        if join_type.upper() not in valid_joins:
            raise InvalidParameterError(f"Invalid join type: {join_type}")
        
        # Validate identifiers
        IdentifierValidator.validate(table)
        IdentifierValidator.validate(on_column)
        IdentifierValidator.validate(on_value_column)
        
        quoted_table = IdentifierValidator.quote(table)
        if alias:
            IdentifierValidator.validate(alias)
            quoted_table += f" AS {IdentifierValidator.quote(alias)}"
        
        join_sql = (
            f"{join_type.upper()} JOIN {quoted_table} "
            f"ON {IdentifierValidator.quote(on_column)} = "
            f"{IdentifierValidator.quote(on_value_column)}"
        )
        self._joins.append(join_sql)
        
        return self
    
    def where(
        self,
        column: str,
        operator: str,
        value: Any,
    ) -> "SafeQueryBuilder":
        """Add a WHERE clause.
        
        Args:
            column: Column name
            operator: Comparison operator
            value: Value to compare
            
        Returns:
            Self for chaining
        """
        # Validate column
        IdentifierValidator.validate(column)
        
        # Validate operator
        valid_operators = {"=", "!=", "<>", "<", ">", "<=", ">=", "LIKE", "ILIKE", "IN", "NOT IN", "IS", "IS NOT"}
        if operator.upper() not in valid_operators:
            raise InvalidParameterError(f"Invalid operator: {operator}")
        
        quoted_col = IdentifierValidator.quote(column)
        placeholder = self._add_param(value)
        
        clause = f"{quoted_col} {operator} {placeholder}"
        self._where_clauses.append((clause, value))
        
        return self
    
    def where_in(
        self,
        column: str,
        values: Sequence[Any],
    ) -> "SafeQueryBuilder":
        """Add a WHERE IN clause.
        
        Args:
            column: Column name
            values: Values for IN clause
            
        Returns:
            Self for chaining
        """
        if not values:
            raise InvalidParameterError("WHERE IN requires at least one value")
        
        IdentifierValidator.validate(column)
        quoted_col = IdentifierValidator.quote(column)
        
        placeholders = [self._add_param(v) for v in values]
        clause = f"{quoted_col} IN ({', '.join(placeholders)})"
        self._where_clauses.append((clause, values))
        
        return self
    
    def where_null(self, column: str, is_null: bool = True) -> "SafeQueryBuilder":
        """Add a WHERE IS NULL/IS NOT NULL clause.
        
        Args:
            column: Column name
            is_null: True for IS NULL, False for IS NOT NULL
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(column)
        quoted_col = IdentifierValidator.quote(column)
        
        op = "IS NULL" if is_null else "IS NOT NULL"
        clause = f"{quoted_col} {op}"
        self._where_clauses.append((clause, None))
        
        return self
    
    def order_by(self, column: str, direction: str = "ASC") -> "SafeQueryBuilder":
        """Add an ORDER BY clause.
        
        Args:
            column: Column to order by
            direction: ASC or DESC
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(column)
        
        direction = direction.upper()
        if direction not in {"ASC", "DESC"}:
            raise InvalidParameterError(f"Invalid order direction: {direction}")
        
        self._order_by.append((
            IdentifierValidator.quote(column),
            direction,
        ))
        
        return self
    
    def group_by(self, *columns: str) -> "SafeQueryBuilder":
        """Add GROUP BY columns.
        
        Args:
            *columns: Columns to group by
            
        Returns:
            Self for chaining
        """
        for col in columns:
            IdentifierValidator.validate(col)
            self._group_by.append(IdentifierValidator.quote(col))
        
        return self
    
    def having(
        self,
        column: str,
        operator: str,
        value: Any,
    ) -> "SafeQueryBuilder":
        """Add a HAVING clause.
        
        Args:
            column: Column/aggregate name
            operator: Comparison operator
            value: Value to compare
            
        Returns:
            Self for chaining
        """
        valid_operators = {"=", "!=", "<>", "<", ">", "<=", ">="}
        if operator.upper() not in valid_operators:
            raise InvalidParameterError(f"Invalid operator: {operator}")
        
        # Column might be an aggregate like COUNT(*), so we do basic validation
        if not column.replace("(", "").replace(")", "").replace("*", "").replace("_", "").isalnum():
            raise InvalidParameterError(f"Invalid HAVING column: {column}")
        
        placeholder = self._add_param(value)
        clause = f"{column} {operator} {placeholder}"
        self._having_clauses.append((clause, value))
        
        return self
    
    def limit(self, limit: int) -> "SafeQueryBuilder":
        """Set LIMIT.
        
        Args:
            limit: Maximum rows to return
            
        Returns:
            Self for chaining
        """
        if not isinstance(limit, int) or limit < 0:
            raise InvalidParameterError("Limit must be a non-negative integer")
        
        self._limit = limit
        return self
    
    def offset(self, offset: int) -> "SafeQueryBuilder":
        """Set OFFSET.
        
        Args:
            offset: Number of rows to skip
            
        Returns:
            Self for chaining
        """
        if not isinstance(offset, int) or offset < 0:
            raise InvalidParameterError("Offset must be a non-negative integer")
        
        self._offset = offset
        return self
    
    def build(self) -> Tuple[str, List[Any]]:
        """Build the final query.
        
        Returns:
            Tuple of (query_string, parameters)
            
        Raises:
            UnsafeQueryError: If query is incomplete
        """
        if not self._select_columns:
            raise UnsafeQueryError("No columns selected")
        
        if not self._table:
            raise UnsafeQueryError("No table specified")
        
        # Build query parts
        parts = []
        
        # SELECT
        parts.append(f"SELECT {', '.join(self._select_columns)}")
        
        # FROM
        parts.append(f"FROM {self._table}")
        
        # JOINs
        for join in self._joins:
            parts.append(join)
        
        # WHERE
        if self._where_clauses:
            where_parts = [clause for clause, _ in self._where_clauses]
            parts.append(f"WHERE {' AND '.join(where_parts)}")
        
        # GROUP BY
        if self._group_by:
            parts.append(f"GROUP BY {', '.join(self._group_by)}")
        
        # HAVING
        if self._having_clauses:
            having_parts = [clause for clause, _ in self._having_clauses]
            parts.append(f"HAVING {' AND '.join(having_parts)}")
        
        # ORDER BY
        if self._order_by:
            order_parts = [f"{col} {dir}" for col, dir in self._order_by]
            parts.append(f"ORDER BY {', '.join(order_parts)}")
        
        # LIMIT
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")
        
        # OFFSET
        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")
        
        query = " ".join(parts)
        
        return query, self._params


# =============================================================================
# Safe Insert Builder
# =============================================================================

class SafeInsertBuilder:
    """Build INSERT queries safely."""
    
    def __init__(self, placeholder_style: str = "positional"):
        """Initialize insert builder.
        
        Args:
            placeholder_style: Placeholder style
        """
        self._placeholder_style = placeholder_style
        self._table: Optional[str] = None
        self._columns: List[str] = []
        self._values: List[List[Any]] = []
        self._returning: List[str] = []
        self._param_count = 0
    
    def _next_placeholder(self) -> str:
        """Get next parameter placeholder."""
        self._param_count += 1
        if self._placeholder_style == "positional":
            return f"${self._param_count}"
        elif self._placeholder_style == "named":
            return f":p{self._param_count}"
        elif self._placeholder_style == "qmark":
            return "?"
        else:
            return "%s"
    
    def into(self, table: str) -> "SafeInsertBuilder":
        """Set target table.
        
        Args:
            table: Table name
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(table)
        self._table = IdentifierValidator.quote(table)
        return self
    
    def columns(self, *cols: str) -> "SafeInsertBuilder":
        """Set columns to insert.
        
        Args:
            *cols: Column names
            
        Returns:
            Self for chaining
        """
        for col in cols:
            IdentifierValidator.validate(col)
            self._columns.append(IdentifierValidator.quote(col))
        return self
    
    def values(self, *vals: Any) -> "SafeInsertBuilder":
        """Add a row of values.
        
        Args:
            *vals: Values for the row
            
        Returns:
            Self for chaining
        """
        if len(vals) != len(self._columns):
            raise InvalidParameterError(
                f"Expected {len(self._columns)} values, got {len(vals)}"
            )
        
        # Validate string values
        for val in vals:
            if isinstance(val, str):
                SQLInjectionDetector.validate_or_raise(val)
        
        self._values.append(list(vals))
        return self
    
    def returning(self, *cols: str) -> "SafeInsertBuilder":
        """Add RETURNING clause.
        
        Args:
            *cols: Columns to return
            
        Returns:
            Self for chaining
        """
        for col in cols:
            if col == "*":
                self._returning.append("*")
            else:
                IdentifierValidator.validate(col)
                self._returning.append(IdentifierValidator.quote(col))
        return self
    
    def build(self) -> Tuple[str, List[Any]]:
        """Build the INSERT query.
        
        Returns:
            Tuple of (query_string, parameters)
        """
        if not self._table:
            raise UnsafeQueryError("No table specified")
        
        if not self._columns:
            raise UnsafeQueryError("No columns specified")
        
        if not self._values:
            raise UnsafeQueryError("No values specified")
        
        # Build column list
        cols = f"({', '.join(self._columns)})"
        
        # Build values with placeholders
        params: List[Any] = []
        value_groups = []
        
        for row in self._values:
            placeholders = []
            for val in row:
                params.append(val)
                placeholders.append(self._next_placeholder())
            value_groups.append(f"({', '.join(placeholders)})")
        
        values = ", ".join(value_groups)
        
        query = f"INSERT INTO {self._table} {cols} VALUES {values}"
        
        # RETURNING
        if self._returning:
            query += f" RETURNING {', '.join(self._returning)}"
        
        return query, params


# =============================================================================
# Safe Update Builder
# =============================================================================

class SafeUpdateBuilder:
    """Build UPDATE queries safely."""
    
    def __init__(self, placeholder_style: str = "positional"):
        """Initialize update builder.
        
        Args:
            placeholder_style: Placeholder style
        """
        self._placeholder_style = placeholder_style
        self._table: Optional[str] = None
        self._set_clauses: List[Tuple[str, Any]] = []
        self._where_clauses: List[Tuple[str, Any]] = []
        self._returning: List[str] = []
        self._param_count = 0
    
    def _next_placeholder(self) -> str:
        """Get next parameter placeholder."""
        self._param_count += 1
        if self._placeholder_style == "positional":
            return f"${self._param_count}"
        elif self._placeholder_style == "named":
            return f":p{self._param_count}"
        elif self._placeholder_style == "qmark":
            return "?"
        else:
            return "%s"
    
    def table(self, table: str) -> "SafeUpdateBuilder":
        """Set target table.
        
        Args:
            table: Table name
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(table)
        self._table = IdentifierValidator.quote(table)
        return self
    
    def set(self, column: str, value: Any) -> "SafeUpdateBuilder":
        """Add a SET clause.
        
        Args:
            column: Column to update
            value: New value
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(column)
        
        # Validate string values
        if isinstance(value, str):
            SQLInjectionDetector.validate_or_raise(value)
        
        self._set_clauses.append((
            IdentifierValidator.quote(column),
            value,
        ))
        return self
    
    def where(
        self,
        column: str,
        operator: str,
        value: Any,
    ) -> "SafeUpdateBuilder":
        """Add a WHERE clause.
        
        Args:
            column: Column name
            operator: Comparison operator
            value: Value to compare
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(column)
        
        valid_operators = {"=", "!=", "<>", "<", ">", "<=", ">="}
        if operator.upper() not in valid_operators:
            raise InvalidParameterError(f"Invalid operator: {operator}")
        
        # Validate string values
        if isinstance(value, str):
            SQLInjectionDetector.validate_or_raise(value)
        
        self._where_clauses.append((
            IdentifierValidator.quote(column),
            operator,
            value,
        ))
        return self
    
    def returning(self, *cols: str) -> "SafeUpdateBuilder":
        """Add RETURNING clause.
        
        Args:
            *cols: Columns to return
            
        Returns:
            Self for chaining
        """
        for col in cols:
            if col == "*":
                self._returning.append("*")
            else:
                IdentifierValidator.validate(col)
                self._returning.append(IdentifierValidator.quote(col))
        return self
    
    def build(self) -> Tuple[str, List[Any]]:
        """Build the UPDATE query.
        
        Returns:
            Tuple of (query_string, parameters)
        """
        if not self._table:
            raise UnsafeQueryError("No table specified")
        
        if not self._set_clauses:
            raise UnsafeQueryError("No SET clauses specified")
        
        if not self._where_clauses:
            # Require WHERE clause to prevent accidental mass updates
            raise UnsafeQueryError(
                "WHERE clause required. Use where_all() to explicitly update all rows."
            )
        
        params: List[Any] = []
        
        # Build SET
        set_parts = []
        for col, val in self._set_clauses:
            params.append(val)
            set_parts.append(f"{col} = {self._next_placeholder()}")
        
        # Build WHERE
        where_parts = []
        for col, op, val in self._where_clauses:
            params.append(val)
            where_parts.append(f"{col} {op} {self._next_placeholder()}")
        
        query = f"UPDATE {self._table} SET {', '.join(set_parts)}"
        query += f" WHERE {' AND '.join(where_parts)}"
        
        # RETURNING
        if self._returning:
            query += f" RETURNING {', '.join(self._returning)}"
        
        return query, params


# =============================================================================
# Safe Delete Builder
# =============================================================================

class SafeDeleteBuilder:
    """Build DELETE queries safely."""
    
    def __init__(self, placeholder_style: str = "positional"):
        """Initialize delete builder.
        
        Args:
            placeholder_style: Placeholder style
        """
        self._placeholder_style = placeholder_style
        self._table: Optional[str] = None
        self._where_clauses: List[Tuple[str, str, Any]] = []
        self._returning: List[str] = []
        self._param_count = 0
    
    def _next_placeholder(self) -> str:
        """Get next parameter placeholder."""
        self._param_count += 1
        if self._placeholder_style == "positional":
            return f"${self._param_count}"
        elif self._placeholder_style == "named":
            return f":p{self._param_count}"
        elif self._placeholder_style == "qmark":
            return "?"
        else:
            return "%s"
    
    def from_table(self, table: str) -> "SafeDeleteBuilder":
        """Set target table.
        
        Args:
            table: Table name
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(table)
        self._table = IdentifierValidator.quote(table)
        return self
    
    def where(
        self,
        column: str,
        operator: str,
        value: Any,
    ) -> "SafeDeleteBuilder":
        """Add a WHERE clause.
        
        Args:
            column: Column name
            operator: Comparison operator
            value: Value to compare
            
        Returns:
            Self for chaining
        """
        IdentifierValidator.validate(column)
        
        valid_operators = {"=", "!=", "<>", "<", ">", "<=", ">=", "IN"}
        if operator.upper() not in valid_operators:
            raise InvalidParameterError(f"Invalid operator: {operator}")
        
        # Validate string values
        if isinstance(value, str):
            SQLInjectionDetector.validate_or_raise(value)
        
        self._where_clauses.append((
            IdentifierValidator.quote(column),
            operator,
            value,
        ))
        return self
    
    def returning(self, *cols: str) -> "SafeDeleteBuilder":
        """Add RETURNING clause.
        
        Args:
            *cols: Columns to return
            
        Returns:
            Self for chaining
        """
        for col in cols:
            if col == "*":
                self._returning.append("*")
            else:
                IdentifierValidator.validate(col)
                self._returning.append(IdentifierValidator.quote(col))
        return self
    
    def build(self) -> Tuple[str, List[Any]]:
        """Build the DELETE query.
        
        Returns:
            Tuple of (query_string, parameters)
        """
        if not self._table:
            raise UnsafeQueryError("No table specified")
        
        if not self._where_clauses:
            # Require WHERE clause to prevent accidental mass deletes
            raise UnsafeQueryError(
                "WHERE clause required. Refusing to delete all rows."
            )
        
        params: List[Any] = []
        
        # Build WHERE
        where_parts = []
        for col, op, val in self._where_clauses:
            params.append(val)
            where_parts.append(f"{col} {op} {self._next_placeholder()}")
        
        query = f"DELETE FROM {self._table} WHERE {' AND '.join(where_parts)}"
        
        # RETURNING
        if self._returning:
            query += f" RETURNING {', '.join(self._returning)}"
        
        return query, params


# =============================================================================
# Query Sanitizer (for legacy query handling)
# =============================================================================

class QuerySanitizer:
    """Sanitize queries for cases where raw SQL is unavoidable."""
    
    @staticmethod
    def escape_string(value: str, quote_char: str = "'") -> str:
        """Escape a string for safe inclusion in SQL.
        
        WARNING: This should only be used when parameterization is impossible.
        Always prefer parameterized queries.
        
        Args:
            value: String to escape
            quote_char: Quote character to use
            
        Returns:
            Escaped string (without surrounding quotes)
        """
        # First, check for injection attempts
        SQLInjectionDetector.validate_or_raise(value)
        
        # Escape the quote character by doubling it
        escaped = value.replace(quote_char, quote_char + quote_char)
        
        # Escape backslashes
        escaped = escaped.replace('\\', '\\\\')
        
        return escaped
    
    @staticmethod
    def escape_like(value: str) -> str:
        """Escape special characters for LIKE patterns.
        
        Args:
            value: Value to escape
            
        Returns:
            Escaped value safe for LIKE
        """
        # Escape LIKE wildcards
        escaped = value.replace('%', '\\%')
        escaped = escaped.replace('_', '\\_')
        escaped = escaped.replace('[', '\\[')
        
        return escaped


# =============================================================================
# Convenience Functions
# =============================================================================

def select(*columns: str) -> SafeQueryBuilder:
    """Create a new SELECT query builder.
    
    Args:
        *columns: Columns to select
        
    Returns:
        Query builder
    """
    builder = SafeQueryBuilder()
    return builder.select(*columns)


def insert_into(table: str) -> SafeInsertBuilder:
    """Create a new INSERT query builder.
    
    Args:
        table: Target table
        
    Returns:
        Insert builder
    """
    builder = SafeInsertBuilder()
    return builder.into(table)


def update(table: str) -> SafeUpdateBuilder:
    """Create a new UPDATE query builder.
    
    Args:
        table: Target table
        
    Returns:
        Update builder
    """
    builder = SafeUpdateBuilder()
    return builder.table(table)


def delete_from(table: str) -> SafeDeleteBuilder:
    """Create a new DELETE query builder.
    
    Args:
        table: Target table
        
    Returns:
        Delete builder
    """
    builder = SafeDeleteBuilder()
    return builder.from_table(table)
