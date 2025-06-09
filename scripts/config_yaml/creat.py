import os.path
import sys

from toll_box.jsons import read_json, pretty_print_json
from toll_box.logs import start_log, end_log
from toll_box.yamls import write_yaml

DEFAULT_FILE = os.path.join(os.getcwd(), "config.json")


def main(argv):
	start_log()
	if not argv:
		input = DEFAULT_FILE
	else:
		input = argv[0]
	
	config_json = read_json(input)
	# for key in config_json.keys():
	# 	pretty_print_json(config_json)
	
	# config_yaml = []
	write_yaml(config_json)
	end_log()


if __name__ == "__main__":
	main(sys.argv[1:])
