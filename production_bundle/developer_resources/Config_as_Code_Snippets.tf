variable "db_tenant_id" {
  default = "demo"
}

resource "postgres_role" "regengine_user" {
  name     = "regengine"
  login    = true
  password = var.db_password
}
