import os
from datetime import datetime

import yaml

DEFAULT_DOWLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
time_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")


def write_yaml(yaml_data, file_name=None):
	if not file_name:
		tmp_name = f"config_{time_stamp}.yaml"
		file_name = os.path.join(DEFAULT_DOWLOAD_DIR, tmp_name)
		print(file_name)
		os.makedirs(os.path.dirname(file_name), exist_ok=True)
	
	yaml_output = yaml.dump(yaml_data, sort_keys=False)
	print(yaml_output)
	
	with open(file_name, 'w') as f:
		f.write(yaml_output)
