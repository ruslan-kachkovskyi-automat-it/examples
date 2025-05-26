packer {
  required_plugins {
    amazon = {
      version = ">= 1.3.6"
      source  = "github.com/hashicorp/amazon"
    }
    ansible = {
      version = ">= 1.1.3"
      source  = "github.com/hashicorp/ansible"
    }
  }
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

source "amazon-ebs" "worker" {
  ami_name = "worker-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  instance_type        = "t4g.small"
  ssh_username         = "ubuntu"
  iam_instance_profile = ""

  associate_public_ip_address = true
  region                      = var.region

  source_ami_filter {
    filters = {
      virtualization-type = "hvm"
      name                = "ubuntu/images/hvm*/ubuntu-noble-24.04*"
      root-device-type    = "ebs"
      architecture        = "arm64"
    }
    owners      = ["amazon"]
    most_recent = true
  }

  subnet_filter {
    filters = {
      "tag:Network" : "Public"
    }
    most_free = true
    random    = false
  }
}

build {
  sources = ["amazon-ebs.worker"]

  provisioner "ansible" {
    playbook_file = "./ansible.yml"
  }
}
