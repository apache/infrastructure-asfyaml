# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Tests for branch protection pattern matching functionality"""

import pytest
import re
import strictyaml
from asfyaml.feature.github.branch_protection import (
    compile_protection_rules,
    match_branches_to_patterns,
    resolve_protection_rules
)
from asfyaml.validators import BranchPattern


class TestPatternCompilation:
    """Test regex pattern compilation and validation"""
    
    def test_valid_pattern_rules(self):
        """Test compilation of valid pattern rules"""
        branches_config = {
            "feature-branches": {
                "pattern": "feature/.*",
                "required_signatures": True
            },
            "release-branches": {
                "pattern": r"release/v\d+\.\d+",
                "required_linear_history": True
            }
        }
        
        pattern_rules, exact_rules = compile_protection_rules(branches_config)
        
        assert len(pattern_rules) == 2
        assert len(exact_rules) == 0
        
        assert "feature-branches" in pattern_rules
        assert "release-branches" in pattern_rules
        
        # Test that regex objects are compiled
        assert isinstance(pattern_rules["feature-branches"]["regex"], re.Pattern)
        assert isinstance(pattern_rules["release-branches"]["regex"], re.Pattern)
    
    def test_mixed_pattern_and_exact_rules(self):
        """Test compilation with both pattern and exact rules"""
        branches_config = {
            "main": {
                "required_signatures": True
            },
            "develop": {
                "required_pull_request_reviews": {
                    "required_approving_review_count": 2
                }
            },
            "feature-branches": {
                "pattern": "feature/.*",
                "required_signatures": False
            }
        }
        
        pattern_rules, exact_rules = compile_protection_rules(branches_config)
        
        assert len(pattern_rules) == 1
        assert len(exact_rules) == 2
        
        assert "feature-branches" in pattern_rules
        assert "main" in exact_rules
        assert "develop" in exact_rules
    
    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex patterns"""
        branches_config = {
            "bad-pattern": {
                "pattern": "feature/[invalid",
                "required_signatures": True
            }
        }
        
        with pytest.raises(Exception, match="Invalid regex pattern"):
            compile_protection_rules(branches_config)
    
    def test_empty_pattern(self):
        """Test handling of empty pattern"""
        branches_config = {
            "empty-pattern": {
                "pattern": "",
                "required_signatures": True
            }
        }
        
        # Should not raise exception at compilation (validation happens at schema level)
        pattern_rules, exact_rules = compile_protection_rules(branches_config)
        assert len(pattern_rules) == 1


class TestBranchMatching:
    """Test branch matching against patterns"""
    
    def test_simple_pattern_matching(self):
        """Test basic pattern matching"""
        pattern_rules = {
            "feature-branches": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*",
                "settings": {"required_signatures": True}
            }
        }
        
        branches = ["main", "feature/auth", "feature/payment", "hotfix/urgent"]
        matches = match_branches_to_patterns(branches, pattern_rules)
        
        assert len(matches) == 2
        assert "feature/auth" in matches
        assert "feature/payment" in matches
        assert matches["feature/auth"] == ["feature-branches"]
        assert matches["feature/payment"] == ["feature-branches"]
    
    def test_multiple_patterns_single_branch(self):
        """Test single branch matching multiple patterns"""
        pattern_rules = {
            "all-branches": {
                "regex": re.compile(".*"),
                "pattern_str": ".*",
                "settings": {"required_signatures": True}
            },
            "feature-branches": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*", 
                "settings": {"required_pull_request_reviews": True}
            }
        }
        
        branches = ["feature/auth", "main"]
        matches = match_branches_to_patterns(branches, pattern_rules)
        
        assert len(matches) == 2
        assert len(matches["feature/auth"]) == 2
        assert len(matches["main"]) == 1
        assert "all-branches" in matches["feature/auth"]
        assert "feature-branches" in matches["feature/auth"]
    
    def test_complex_patterns(self):
        """Test complex regex patterns"""
        pattern_rules = {
            "version-releases": {
                "regex": re.compile(r"release/v\d+\.\d+"),
                "pattern_str": r"release/v\d+\.\d+",
                "settings": {"required_signatures": True}
            },
            "user-branches": {
                "regex": re.compile(r"users/[^/]+/.*"),
                "pattern_str": r"users/[^/]+/.*",
                "settings": {"required_pull_request_reviews": True}
            }
        }
        
        branches = [
            "release/v1.0", "release/v2.1", "release/beta",
            "users/john/feature", "users/jane/hotfix", "feature/auth"
        ]
        matches = match_branches_to_patterns(branches, pattern_rules)
        
        assert len(matches) == 4
        assert "release/v1.0" in matches
        assert "release/v2.1" in matches
        assert "users/john/feature" in matches
        assert "users/jane/hotfix" in matches
        assert "release/beta" not in matches
        assert "feature/auth" not in matches


class TestRuleResolution:
    """Test final rule resolution with precedence"""
    
    def test_exact_overrides_pattern(self):
        """Test exact branch rules override pattern matches"""
        all_branches = {
            "main": {"name": "main"},
            "feature/auth": {"name": "feature/auth"},
            "feature/payment": {"name": "feature/payment"}
        }
        
        pattern_rules = {
            "all-branches": {
                "regex": re.compile(".*"),
                "pattern_str": ".*",
                "settings": {"required_signatures": False}
            }
        }
        
        exact_rules = {
            "main": {"required_signatures": True}
        }
        
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        assert len(final_rules) == 3
        assert final_rules["main"]["rule_type"] == "exact"
        assert final_rules["main"]["settings"]["required_signatures"] is True
        assert final_rules["feature/auth"]["rule_type"] == "pattern"
        assert final_rules["feature/auth"]["settings"]["required_signatures"] is False
        
        # Should warn about exact rule overriding pattern
        assert any("overrides pattern match" in w for w in warnings)
    
    def test_first_pattern_wins_conflicts(self):
        """Test first matching pattern wins for conflicts"""
        all_branches = {
            "feature/auth": {"name": "feature/auth"}
        }
        
        # Order matters - first pattern should win
        pattern_rules = {
            "first-pattern": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*",
                "settings": {"required_signatures": True}
            },
            "second-pattern": {
                "regex": re.compile(".*"),
                "pattern_str": ".*", 
                "settings": {"required_signatures": False}
            }
        }
        
        exact_rules = {}
        
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        assert len(final_rules) == 1
        assert final_rules["feature/auth"]["settings"]["required_signatures"] is True
        assert "first-pattern" in final_rules["feature/auth"]["source"]
        
        # Should warn about multiple pattern matches
        assert any("matches multiple patterns" in w for w in warnings)
    
    def test_pattern_no_matches_warning(self):
        """Test warning when pattern matches no branches"""
        all_branches = {
            "main": {"name": "main"}
        }
        
        pattern_rules = {
            "feature-branches": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*",
                "settings": {"required_signatures": True}
            }
        }
        
        exact_rules = {}
        
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        assert len(final_rules) == 0
        assert any("matches no branches" in w for w in warnings)
    
    def test_exact_branch_not_found_warning(self):
        """Test warning when exact branch doesn't exist"""
        all_branches = {
            "main": {"name": "main"}
        }
        
        pattern_rules = {}
        exact_rules = {
            "nonexistent": {"required_signatures": True}
        }
        
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        assert len(final_rules) == 0
        assert any("does not match any existing branch" in w for w in warnings)


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""
    
    def test_typical_project_setup(self):
        """Test a typical project branch protection setup"""
        all_branches = {
            "main": {"name": "main"},
            "develop": {"name": "develop"},
            "feature/user-auth": {"name": "feature/user-auth"},
            "feature/payment": {"name": "feature/payment"},
            "release/v1.0": {"name": "release/v1.0"},
            "hotfix/security-fix": {"name": "hotfix/security-fix"}
        }
        
        branches_config = {
            "main": {
                "required_signatures": True,
                "required_linear_history": True
            },
            "develop": {
                "required_pull_request_reviews": {
                    "required_approving_review_count": 1
                }
            },
            "feature-branches": {
                "pattern": "feature/.*",
                "required_pull_request_reviews": {
                    "required_approving_review_count": 1
                }
            },
            "release-branches": {
                "pattern": r"release/.*",
                "required_signatures": True
            },
            "hotfix-branches": {
                "pattern": "hotfix/.*",
                "required_pull_request_reviews": {
                    "required_approving_review_count": 2
                }
            }
        }
        
        pattern_rules, exact_rules = compile_protection_rules(branches_config)
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        # Verify all branches get protection
        assert len(final_rules) == 6
        
        # Check exact rules
        assert final_rules["main"]["rule_type"] == "exact"
        assert final_rules["main"]["settings"]["required_signatures"] is True
        assert final_rules["develop"]["rule_type"] == "exact"
        
        # Check pattern matches
        assert final_rules["feature/user-auth"]["rule_type"] == "pattern"
        assert final_rules["feature/payment"]["rule_type"] == "pattern"
        assert final_rules["release/v1.0"]["rule_type"] == "pattern" 
        assert final_rules["hotfix/security-fix"]["rule_type"] == "pattern"
        
        # Verify settings are correctly applied
        assert final_rules["release/v1.0"]["settings"]["required_signatures"] is True
        assert final_rules["hotfix/security-fix"]["settings"]["required_pull_request_reviews"]["required_approving_review_count"] == 2
        
        # Should have minimal warnings
        assert len(warnings) == 0


class TestBranchPatternValidator:
    """Test the BranchPattern validator class"""
    
    def test_validator_valid_patterns(self):
        """Test validator accepts valid regex patterns"""
        validator = BranchPattern()
        
        class MockChunk:
            def __init__(self, contents):
                self.contents = contents
        
        # Test various valid patterns
        valid_patterns = [
            "feature/.*",
            r"release/v\d+\.\d+", 
            "hotfix/.*",
            r"users/[^/]+/.*",
            ".*",
            "main",
            "develop"
        ]
        
        for pattern in valid_patterns:
            chunk = MockChunk(pattern)
            result = validator.validate_scalar(chunk)
            assert result == pattern
    
    def test_validator_invalid_regex(self):
        """Test validator rejects invalid regex patterns"""
        validator = BranchPattern()
        
        class MockChunk:
            def __init__(self, contents):
                self.contents = contents
            
            def expecting_but_found(self, message):
                # StrictYAML expects different arguments
                raise Exception(message)
        
        invalid_patterns = [
            "feature/[invalid",  # Missing closing bracket
            "release/(unclosed",  # Unclosed parenthesis  
        ]
        
        for pattern in invalid_patterns:
            chunk = MockChunk(pattern)
            with pytest.raises(Exception, match="invalid regex pattern"):
                validator.validate_scalar(chunk)
        
        # Test that valid patterns don't raise (sanity check)
        valid_chunk = MockChunk("hotfix/.*")
        result = validator.validate_scalar(valid_chunk)
        assert result == "hotfix/.*"
    
    def test_validator_empty_pattern(self):
        """Test validator rejects empty patterns"""
        validator = BranchPattern()
        
        class MockChunk:
            def __init__(self, contents):
                self.contents = contents
                
            def expecting_but_found(self, message):
                raise Exception(message)
        
        chunk = MockChunk("")
        with pytest.raises(Exception, match="pattern cannot be empty"):
            validator.validate_scalar(chunk)
    
    def test_validator_pattern_too_long(self):
        """Test validator rejects patterns that are too long (ReDoS protection)"""
        validator = BranchPattern()
        
        class MockChunk:
            def __init__(self, contents):
                self.contents = contents
                
            def expecting_but_found(self, message):
                raise Exception(message)
        
        # Create a pattern longer than MAX_PATTERN_LENGTH (1000)
        long_pattern = "a" * 1001
        chunk = MockChunk(long_pattern)
        
        with pytest.raises(Exception, match="pattern too long"):
            validator.validate_scalar(chunk)
    
    def test_validator_to_yaml(self):
        """Test validator's to_yaml method"""
        validator = BranchPattern()
        assert validator.to_yaml("feature/.*") == "feature/.*"
        assert validator.to_yaml("main") == "main"


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_compile_rules_with_invalid_regex_in_runtime(self):
        """Test runtime regex compilation errors are handled"""
        # This tests the secondary validation in compile_protection_rules
        # even if something slips past the schema validator
        
        # Mock a scenario where invalid regex gets through
        branches_config = {
            "bad-rule": {
                "pattern": "[invalid-regex",
                "required_signatures": True
            }
        }
        
        with pytest.raises(Exception, match="Invalid regex pattern"):
            compile_protection_rules(branches_config)
    
    def test_match_branches_empty_pattern_rules(self):
        """Test matching with empty pattern rules"""
        branches = ["main", "feature/auth"]
        pattern_rules = {}
        
        matches = match_branches_to_patterns(branches, pattern_rules)
        assert len(matches) == 0
    
    def test_match_branches_empty_branches(self):
        """Test matching with no branches"""
        branches = []
        pattern_rules = {
            "feature-branches": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*",
                "settings": {"required_signatures": True}
            }
        }
        
        matches = match_branches_to_patterns(branches, pattern_rules)
        assert len(matches) == 0
    
    def test_resolve_rules_empty_inputs(self):
        """Test rule resolution with empty inputs"""
        all_branches = {}
        pattern_rules = {}
        exact_rules = {}
        
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        assert len(final_rules) == 0
        assert len(warnings) == 0
    
    def test_resolve_rules_comprehensive_warnings(self):
        """Test all warning scenarios in rule resolution"""
        all_branches = {
            "main": {"name": "main"},
            "feature/overlap": {"name": "feature/overlap"}
        }
        
        # Multiple overlapping patterns
        pattern_rules = {
            "all-branches": {
                "regex": re.compile(".*"),
                "pattern_str": ".*",
                "settings": {"required_signatures": True}
            },
            "feature-branches": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*",
                "settings": {"required_signatures": False}
            },
            "no-match-pattern": {
                "regex": re.compile("nonexistent/.*"),
                "pattern_str": "nonexistent/.*", 
                "settings": {"required_signatures": True}
            }
        }
        
        # Exact rule that overrides pattern and one that doesn't match
        exact_rules = {
            "feature/overlap": {"required_signatures": True},
            "nonexistent-branch": {"required_signatures": True}
        }
        
        final_rules, warnings = resolve_protection_rules(all_branches, pattern_rules, exact_rules)
        
        # Should generate all types of warnings
        warning_types = {
            "multiple patterns": False,
            "overrides pattern": False, 
            "matches no branches": False,
            "does not match any existing": False
        }
        
        for warning in warnings:
            for warning_type in warning_types:
                if warning_type in warning:
                    warning_types[warning_type] = True
        
        # Verify all warning types were generated
        for warning_type, found in warning_types.items():
            assert found, f"Missing warning type: {warning_type}"


class TestPerformanceAndComplexity:
    """Test performance aspects and complex scenarios"""
    
    def test_large_branch_set_performance(self):
        """Test performance with large number of branches"""
        # Simulate a large repository with many branches
        branches = []
        for i in range(1000):
            branches.extend([
                f"feature/feature-{i}",
                f"release/v{i//100}.{i%100}",
                f"hotfix/fix-{i}",
                f"users/user{i}/branch"
            ])
        
        pattern_rules = {
            "feature-branches": {
                "regex": re.compile("feature/.*"),
                "pattern_str": "feature/.*",
                "settings": {"required_signatures": True}
            },
            "release-branches": {
                "regex": re.compile(r"release/v\d+\.\d+"),
                "pattern_str": r"release/v\d+\.\d+",
                "settings": {"required_signatures": True}
            }
        }
        
        # This should complete quickly even with many branches
        matches = match_branches_to_patterns(branches, pattern_rules)
        
        # Verify correct matches
        assert len(matches) == 2000  # 1000 feature + 1000 release (only these patterns match)
        
        # Sample check
        assert "feature/feature-0" in matches
        assert "release/v0.0" in matches
        assert len(matches["feature/feature-0"]) == 1
        assert matches["feature/feature-0"][0] == "feature-branches"
    
    def test_complex_regex_patterns(self):
        """Test complex real-world regex patterns"""
        complex_patterns = {
            "semantic-versions": {
                "regex": re.compile(r"release/v\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?"),
                "pattern_str": r"release/v\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?",
                "settings": {"required_signatures": True}
            },
            "user-feature-branches": {
                "regex": re.compile(r"users/[a-zA-Z][a-zA-Z0-9_-]*/feature/.*"),
                "pattern_str": r"users/[a-zA-Z][a-zA-Z0-9_-]*/feature/.*",
                "settings": {"required_pull_request_reviews": True}
            },
            "date-based-branches": {
                "regex": re.compile(r"sprint/\d{4}-\d{2}-\d{2}/.*"),
                "pattern_str": r"sprint/\d{4}-\d{2}-\d{2}/.*",
                "settings": {"required_linear_history": True}
            }
        }
        
        test_branches = [
            "release/v1.2.3",
            "release/v1.2.3-beta",
            "release/v1.2.3-rc1",
            "users/john_doe/feature/auth",
            "users/jane-smith/feature/payment",
            "users/123invalid/feature/test",  # Should not match (starts with digit)
            "sprint/2024-01-15/planning",
            "sprint/2024-12-31/retrospective",
            "main",
            "develop"
        ]
        
        matches = match_branches_to_patterns(test_branches, complex_patterns)
        
        # Verify semantic version matches
        assert "release/v1.2.3" in matches
        assert "release/v1.2.3-beta" in matches
        assert "release/v1.2.3-rc1" in matches
        
        # Verify user branch matches (valid usernames only)
        assert "users/john_doe/feature/auth" in matches
        assert "users/jane-smith/feature/payment" in matches
        assert "users/123invalid/feature/test" not in matches  # Invalid username
        
        # Verify date-based matches
        assert "sprint/2024-01-15/planning" in matches
        assert "sprint/2024-12-31/retrospective" in matches
        
        # Verify non-matches
        assert "main" not in matches
        assert "develop" not in matches