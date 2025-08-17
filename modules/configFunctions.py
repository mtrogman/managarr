import yaml

def get_config(file):
    with open(file, 'r', encoding='utf-8') as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config or {}
