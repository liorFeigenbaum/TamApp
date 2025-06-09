import json
from logging import error


def check_end_code(file_path):
	with open(file_path) as raw_data:
		return raw_data.encoding


def read_json(file_path):
	with open(file_path, "r", encoding=check_end_code(file_path)) as f:
		input_json = json.load(f)
	return input_json


def read_json_multilingual(file_path):
	try:
		with open(file_path, "r", encoding='utf-8') as f:
			input_json = json.load(f)
	except UnicodeDecodeError:
		with open(file_path, "r", encoding='utf-8-sig') as f:
			input_json = json.load(f)
	return input_json


def read_json_utf8_sig(file_path):
	with open(file_path, "r", encoding='utf-8-sig') as f:
		input_json = json.load(f)
	return input_json


def pretty_print_json(json_data):
	if isinstance(json_data, str):
		json_print = json.loads(json_data)
		pretty_print_json(json_print)
	elif type(json_data) == dict:
		json_print = json.dumps(json_data, ensure_ascii=False, indent='\t')
		print(json_print)
	else:
		error('Type Error: The Object\'s type needs to be dict() or str() and not {0}'.format(type(json_data)))
