"""
Cypher queries for framework arbitrage and compliance analysis
"""

# Find overlap between two frameworks
OVERLAP_QUERY = """
MATCH (f1:Framework {name: $framework1})-[:HAS_CONTROL]->(c1:Control)
MATCH (f2:Framework {name: $framework2})-[:HAS_CONTROL]->(c2:Control)
WHERE c1.requirement = c2.requirement
RETURN count(c1) as overlap_count,
       collect({
           from: c1.control_id,
           to: c2.control_id,
           requirement_from: c1.requirement,
           requirement_to: c2.requirement,
           confidence: 1.0
       }) as mappings
"""

# Get total controls in a framework
TOTAL_CONTROLS_QUERY = """
MATCH (f:Framework {name: $framework})-[:HAS_CONTROL]->(c:Control)
RETURN count(c) as total_controls
"""

# Find compliance gaps
GAP_QUERY = """
MATCH (target:Framework {name: $target})-[:HAS_CONTROL]->(tc:Control)
WHERE NOT EXISTS {
    MATCH (current:Framework {name: $current})-[:HAS_CONTROL]->(cc:Control)
    WHERE cc.requirement = tc.requirement
}
RETURN tc.control_id as control_id,
       tc.requirement as control_name,
       tc.description as description,
       tc.effort_hours as estimated_hours
ORDER BY tc.effort_hours DESC
LIMIT 100
"""

# Find related frameworks (existing relationships)
RELATIONSHIPS_QUERY = """
MATCH (f:Framework {name: $framework})
MATCH (f)-[r:MAPS_TO|ALIGNS_WITH]-(related:Framework)
RETURN DISTINCT related.name as framework_id,
       related.name as framework_name,
       type(r) as relationship_type,
       COALESCE(r.strength, 0.5) as strength,
       COALESCE(r.control_overlap, 0) as control_overlap
ORDER BY strength DESC
"""

# Find all frameworks with overlap (dynamic relationship discovery)
DISCOVER_RELATIONSHIPS_QUERY = """
MATCH (f:Framework {name: $framework})-[:HAS_CONTROL]->(c1:Control)
MATCH (other:Framework)-[:HAS_CONTROL]->(c2:Control)
WHERE other.name <> f.name AND c1.requirement = c2.requirement
WITH other, count(c2) as overlap_count
WHERE overlap_count > 5
MATCH (other)-[:HAS_CONTROL]->(total:Control)
WITH other,
     overlap_count,
     count(total) as total_controls,
     toFloat(overlap_count) / count(total) as strength
RETURN other.name as framework_id,
       other.name as framework_name,
       'maps_to' as relationship_type,
       strength,
       overlap_count as control_overlap
ORDER BY strength DESC
LIMIT 10
"""

# Shortest path between frameworks
SHORTEST_PATH_QUERY = """
MATCH path = shortestPath(
    (f1:Framework {name: $from})-[:MAPS_TO|ALIGNS_WITH*..5]-(f2:Framework {name: $to})
)
RETURN path, length(path) as distance
LIMIT 1
"""

# Get all frameworks
ALL_FRAMEWORKS_QUERY = """
MATCH (f:Framework)
RETURN f.name as name,
       f.version as version,
       f.category as category,
       f.description as description
ORDER BY f.name
"""

# Get framework details with controls
FRAMEWORK_DETAILS_QUERY = """
MATCH (f:Framework {name: $framework})-[:HAS_CONTROL]->(c:Control)
RETURN f.name as framework_name,
       f.version as version,
       f.category as category,
       collect({
           control_id: c.control_id,
           requirement: c.requirement,
           description: c.description,
           effort_hours: c.effort_hours
       }) as controls
"""

# Calculate arbitrage value
ARBITRAGE_VALUE_QUERY = """
MATCH (f1:Framework {name: $framework1})-[:HAS_CONTROL]->(c1:Control)
MATCH (f2:Framework {name: $framework2})-[:HAS_CONTROL]->(c2:Control)
WHERE c1.requirement = c2.requirement
WITH count(c1) as overlap,
     sum(c2.effort_hours) as total_hours_saved
RETURN overlap,
       total_hours_saved,
       total_hours_saved / overlap as avg_hours_per_control
"""

# Get coverage percentage
COVERAGE_QUERY = """
MATCH (current:Framework {name: $current})-[:HAS_CONTROL]->(cc:Control)
MATCH (target:Framework {name: $target})-[:HAS_CONTROL]->(tc:Control)
WITH count(DISTINCT tc) as total_target_controls
MATCH (current:Framework {name: $current})-[:HAS_CONTROL]->(cc2:Control)
MATCH (target:Framework {name: $target})-[:HAS_CONTROL]->(tc2:Control)
WHERE cc2.requirement = tc2.requirement
WITH total_target_controls, count(tc2) as covered_controls
RETURN toFloat(covered_controls) / total_target_controls * 100 as coverage_percentage,
       covered_controls,
       total_target_controls
"""
