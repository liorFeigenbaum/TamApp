import os
import yaml

CURR_PATH = os.path.abspath(os.path.dirname(__file__))


def validate_config_yaml(file_path: str):
	return_dictionary = {"ok": True, "tam": False, "skip_calc": False}
	if not os.path.exists(file_path):
		return {"ok": False, "error": "File not found"}

	with open(file_path, 'r') as f:
		config = yaml.safe_load(f)

	defined_connections = config.get('connections', {})

	# ── Validate that every source's connection exists ────────────────────────
	for src_name, src_body in config.get('sources', {}).items():
		conn_ref = src_body.get('connection')
		if conn_ref and conn_ref != 'file' and conn_ref not in defined_connections:
			return {
				"ok": False,
				"error": f"ERROR: source \"{src_name}\" references connection \"{conn_ref}\" which does not exist in connections"
			}

	# ── Validate that all sink references exist in their sections ─────────────
	for sink in config.get('sinks', {}).keys():
		for key, vals in config['sinks'][sink].items():
			if key == 'filename':
				continue
			for val in vals:
				if val not in config.get(key, {}):
					return {"ok": False, "error": f"ERROR: \"{val}\" does not exist in {key}"}

	# ── TAM / skip_calc warnings (checked on last sink — preserve old behaviour)
	last_sink = list(config['sinks'].keys())[-1]
	connection_bucket = config['sinks'][last_sink]['connections'][0]

	if config['connections'][connection_bucket]['bucket'] == 'onebeat-tam':
		return_dictionary["tam"] = True
		return_dictionary["warning"] = f"You are sending the \"{last_sink}\" sink data into \"TAM\" bucket!!"

	if 'skip_calc' in config['sinks'][last_sink]['filename'].split('/')[-1]:
		return_dictionary["skip_calc"] = True
		return_dictionary["skip"] = f"You are sending the {last_sink} with skip_calc!!"

	return return_dictionary
