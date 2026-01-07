import os.path
import sys

from toll_box.jsons import read_json, pretty_print_json
from toll_box.logs import start_log, end_log
from toll_box.yamls import write_yaml

DEFAULT_FILE = os.path.join(os.getcwd(), "config.json")


def get_transforms(config_json):
	params = ['transform_name[]','transform_type[]','transform_file[]']
	names = config_json['transform_name[]']
	types = config_json['transform_type[]']
	files = config_json['transform_file[]']
	trnasforms = dict()
	
	for x in range(len(names)):
		trnasforms[names[x]] = {'type': types[x], 'file': files[x]}
	
	for ket in params:
		config_json.pop(ket, None)
		
	# print(trnasforms)
	return trnasforms, config_json

def get_sink(config_json):
	sinks = dict()
	sinks[config_json['sink_name'][0]] = {}
	config_json.pop('sink_name', None)
	
	
	pretty_print_json(sinks)
	pass


def main(argv):
	start_log()
	if not argv:
		input = DEFAULT_FILE
	else:
		input = argv[0]
	
	config_json = read_json(input)
	config_json.pop('client_name', None)
	config_json.pop('client_id', None)
	
	trnasforms, config_json = get_transforms(config_json)
	conections = dict()
	sources = dict()
	transforms = dict()
	sinks = dict()
	sources[config_json["mapper_name"][0]] = {
		'type': config_json['mapper_type'][0], 'file': config_json['mapper_path'][0]
		}
	config_keys = [key for key in config_json.keys() if key.startswith("mapper")]
	for key in config_keys:
		if 'mapper' in key:
			config_json.pop(key)
	
	transforms, config_json = get_transforms(config_json)
	get_sink(config_json)
	# pretty_print_json(sources)
	# for key in config_json.keys():
	# 	pretty_print_json(config_json)
	
	# config_yaml = []
	write_yaml(config_json)
	# end_log()


if __name__ == "__main__":
	main(sys.argv[1:])
