import os.path
import sys

from toll_box.jsons import read_json, pretty_print_json
from toll_box.logs import start_log, end_log
from toll_box.yamls import write_yaml

DEFAULT_FILE = os.path.join(os.getcwd(), "config.json")


def get_transforms(config_json):
	params = ['transform_name[]', 'transform_type[]', 'transform_file[]']
	names = config_json['transform_name[]']
	types = config_json['transform_type[]']
	files = config_json['transform_file[]']
	trnasforms = dict()
	
	for x in range(len(names)):
		trnasforms[names[x]] = {'type': types[x], 'file': files[x]}
	
	for ket in params:
		config_json.pop(ket, None)
	
	# print(trnasforms)
	return trnasforms


def get_sink(config_json):
	sinks = dict()
	name = config_json['sink_name'][0]
	sinks[name] = dict()
	sinks[name]['sources'] = config_json["sink_sources[]"]
	if len(config_json["sink_transform[]"]) > 0:
		sinks[name]['transforms'] = config_json["sink_transform[]"]
	sinks[name]['filename'] = config_json["sink_file_name"][0]
	sinks[name]['connections'] = [config_json["sink_connection_selector"][0]]
	sink_keys = [key for key in config_json.keys() if 'sink_' in key]
	for key in sink_keys:
		config_json.pop(key, None)
	
	return sinks


def get_sources(config_json):
	sources = dict()
	keys_to = [key for key in config_json.keys() if key.startswith("source_")]
	names = config_json['source_name[]']
	types = config_json['source_type[]']
	time_offset = config_json['source_time_offset[]']
	path = config_json['source_path[]']
	connection = config_json['source_connection[]']
	
	
	for x in range(len(names)):
		name = names[x]
		sources[name] = dict()
		sources[name]['type'] = types[x]
		if types[x] == 'file':
			sources[name]['connections'] = 'file'
			connection.insert(x, 'file')
		else:
			sources[name]['connections'] = connection[x]
		sources[name]['path'] = path[x]
	
	for key in keys_to:
		config_json.pop(key, None)
	
	for source in sources.keys():
		if 'time_offset' in sources[source] and sources[source]['time_offset'] == 0:
			sources[source].pop('time_offset')
	
	return sources


def get_connections(config_json):
	connections = dict()
	types = [
		key.removesuffix("_name[]")
		for key in config_json.keys()
		if key.endswith("_name[]")
		]
	
	for type in types:
		# print(type)
		attributes = [key for key in config_json.keys() if key.startswith(type) and not key.endswith("_name[]")]
		names = config_json[type+"_name[]"]
		for x in range(len(names)):
			name = names[x]
			connections[name] = dict()
			for attribute in attributes:
				new_key = attribute.split("_")[1].removesuffix("[]")
				connections[name][new_key] = config_json[attribute][x]
				# config_json.pop(attribute, None)
		config_json.pop(type+"_name[]", None)
		for pop in attributes:
			config_json.pop(pop, None)
		# print(names)
		# for attribute in attributes:
		# 	keys
		# print(attribte)
	return connections
	
	pass


def main(argv):
	start_log()
	config_json = dict(argv)
	config_json.pop('client_name', None)
	config_json.pop('client_id', None)
	
	sources = get_sources(config_json)
	transforms = get_transforms(config_json)
	sinks = get_sink(config_json)
	connections = get_connections(config_json)
	
	config_yaml = {
		"connections": connections,
		"sources": sources,
		"transforms": transforms,
		"sinks": sinks,
		}
	write_yaml(config_yaml)
	end_log()
	return config_yaml


if __name__ == "__main__":
	main(sys.argv[1:])
