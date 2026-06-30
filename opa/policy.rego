package lab

import future.keywords.if
import future.keywords.in

# Default deny
default allow := false

# Allowed users
allowed_users := {"alice", "bob", "admin"}

# Allowed actions
allowed_actions := {"read", "list"}

# Admin can do anything
allow if {
    input.user == "admin"
}

# Known users can perform allowed actions
allow if {
    input.user in allowed_users
    input.action in allowed_actions
}