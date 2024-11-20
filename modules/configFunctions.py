import os, yaml, sys

def get_config(file):
    with open(file, 'r') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config