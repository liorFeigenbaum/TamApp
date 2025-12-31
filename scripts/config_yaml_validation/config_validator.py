import os
import yaml

CURR_PATH = os.path.abspath(os.path.dirname(__file__))


def validate_config_yaml(file_path: str):
	clean_config = True
	return_dictionary = {"ok": True, "tam": False, "skip_calc": False}
	if not os.path.exists(file_path):
		return {"ok": False, "error": "File not found"}
	
	with open(file_path, 'r') as f:
		config = yaml.safe_load(f)
		# Checking that all the relevant filed exists in the config.yaml
		for sink in config['sinks'].keys():
			for key in config['sinks'][sink].keys():
				if key != 'filename':
					for val in config['sinks'][sink][key]:
						if val not in config[key].keys():
							try:
								1 / 0
							except Exception as e:
								return {"ok": False, "error": f"ERROR: {val} do not exists in {key}"}
		
		connection_bucket = config['sinks'][sink]['connections'][0]
		
		# Warning when sinking to TAM
		if config['connections'][connection_bucket]['bucket'] == 'onebeat-tam':
			return_dictionary["tam"] = True
			return_dictionary["warning"] = (f"You are sending the \"{sink}\" sink data into \"TAM\" bucket!!")
		
		# Warning when sinking with skip_calc
		if 'skip_calc' in config['sinks'][sink]['filename'].split('/')[-1]:
			return_dictionary["skip_calc"] = True
			return_dictionary["skip"] = (f"Yoou are sending the {sink} with skip_calc!!")
	
	return return_dictionary
