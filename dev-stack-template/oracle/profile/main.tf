terraform {
  required_version = ">= 1.8"
  required_providers {
    oci = { source = "oracle/oci", version = "~> 7.0" }
  }
}
variable "compartment" { type = string }
variable "ssh_cidr" {
  type = string
  validation {
    condition = can(cidrnetmask(var.ssh_cidr)) && endswith(var.ssh_cidr, "/32")
    error_message = "Use your WSL internet connection's public IPv4 address followed by /32."
  }
}
variable "ssh_public_key" { type = string }
variable "ad_index" { default = 0 }
provider "oci" { config_file_profile = "DEFAULT" }
data "oci_identity_availability_domains" "all" { compartment_id = var.compartment }
data "oci_core_images" "ubuntu" {
  compartment_id = var.compartment
  operating_system = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape = "VM.Standard.A1.Flex"
  sort_by = "TIMECREATED"
  sort_order = "DESC"
}
resource "oci_core_vcn" "agent" {
  compartment_id = var.compartment
  cidr_blocks = ["10.83.0.0/24"]
  display_name = "god-inference"
  dns_label = "godinfer"
}
resource "oci_core_internet_gateway" "agent" {
  compartment_id = var.compartment
  vcn_id = oci_core_vcn.agent.id
  enabled = true
}
resource "oci_core_route_table" "agent" {
  compartment_id = var.compartment
  vcn_id = oci_core_vcn.agent.id
  route_rules {
    destination = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.agent.id
  }
}
resource "oci_core_security_list" "agent" {
  compartment_id = var.compartment
  vcn_id = oci_core_vcn.agent.id
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol = "all"
  }
  ingress_security_rules {
    source = var.ssh_cidr
    protocol = "6"
    tcp_options {
      min = 22
      max = 22
    }
  }
}
resource "oci_core_subnet" "agent" {
  compartment_id = var.compartment
  vcn_id = oci_core_vcn.agent.id
  cidr_block = "10.83.0.0/25"
  route_table_id = oci_core_route_table.agent.id
  security_list_ids = [oci_core_security_list.agent.id]
  dns_label = "worker"
}
resource "oci_core_instance" "inference" {
  compartment_id = var.compartment
  availability_domain = data.oci_identity_availability_domains.all.availability_domains[var.ad_index].name
  display_name = "god-inference"
  shape = "VM.Standard.A1.Flex"
  shape_config {
    ocpus = 2
    memory_in_gbs = 12
  }
  create_vnic_details {
    subnet_id = oci_core_subnet.agent.id
    assign_public_ip = true
  }
  source_details {
    source_type = "image"
    source_id = data.oci_core_images.ubuntu.images[0].id
    boot_volume_size_in_gbs = 50
  }
  lifecycle { ignore_changes = [source_details[0].source_id] }
  metadata = { ssh_authorized_keys = var.ssh_public_key }
}
output "ip" { value = oci_core_instance.inference.public_ip }
