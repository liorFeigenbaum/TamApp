import inspect
from logging import info, error


def start_log(name=None):
	if name is None:
		name = inspect.getmodule(inspect.stack()[1][0]).__name__.split('.')[-1]
	info("START: " + name + " start running")


def end_log(err: bool = True, name=None):
	if name is None:
		name = inspect.getmodule(inspect.stack()[1][0]).__name__.split('.')[-1]
	if err:
		info("Done: " + name + " running is over")
	else:
		info("Done: " + name + " running is over with errors")


def file_status(filePath: str, staus):
	fileName = filePath.split('\\')[-1]
	if staus == 'update':
		info("Upadted: " + fileName + " was updated")


def path_error(e, name=None):
	error('Path Error:' + e.__str__()[e.__str__().index(']') + 1:])
	if name is None:
		name = inspect.getmodule(inspect.stack()[1][0]).__name__.split('.')[-1]
	error("Done: " + name + " ended without making any changes")
