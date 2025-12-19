import os
import sys
import re
import json
import ssl
import tempfile
import urllib.request
import urllib.parse
from utilities.util_logger import logger
from utilities.util_powershell_handler import run_powershell_command
from utilities.util_error_popup import show_error_popup



def _is_url(value: str) -> bool:
	try:
		p = urllib.parse.urlparse(value)
		return p.scheme in ("http", "https") and bool(p.netloc)
	except Exception:
		return False



def _download_config(url: str) -> str:
	logger.info(f"Downloading config from: {url}")
	ctx = None
	if url.lower().startswith("https"):
		try:
			import certifi
			ctx = ssl.create_default_context(cafile=certifi.where())
		except Exception:
			ctx = ssl.create_default_context()
	request = urllib.request.Request(url, headers={"User-Agent": "Talon/1.0"})
	with urllib.request.urlopen(request, timeout=30, context=ctx) as resp:
		data = resp.read()
	try:
		json.loads(data.decode("utf-8-sig"))
	except Exception as e:
		raise RuntimeError(f"Downloaded config is not valid JSON: {e}")
	fd, tmp_path = tempfile.mkstemp(prefix="talon_config_", suffix=".json")
	with os.fdopen(fd, "wb") as f:
		f.write(data)
	logger.info(f"Saved downloaded config to: {tmp_path}")
	return tmp_path


def _load_json_config(path: str, label: str):
	try:
		with open(path, "r", encoding="utf-8-sig") as f:
			return json.load(f)
	except Exception as e:
		logger.error(f"Failed to load {label} config: {e}")
		try:
			show_error_popup(
				f"Failed to load {label} config.\n{e}",
				allow_continue=False,
			)
		except Exception:
			pass
		sys.exit(1)


def _write_temp_config(data: dict, prefix: str) -> str:
	fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=".json")
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=4)
	logger.info(f"Saved generated config to: {tmp_path}")
	return tmp_path


def _extract_winutil_config(data):
	if not isinstance(data, dict):
		return None
	if "WinUtil" in data:
		if isinstance(data["WinUtil"], dict):
			return data["WinUtil"]
		logger.warning("WinUtil config is not an object; ignoring.")
		return None
	if "Win11Debloat" in data:
		winutil_data = {key: value for key, value in data.items() if key != "Win11Debloat"}
		if winutil_data:
			return winutil_data
		return None
	return data


def _extract_win11debloat_args(data):
	if not isinstance(data, dict) or "Win11Debloat" not in data:
		return None
	win11 = data["Win11Debloat"]
	if isinstance(win11, dict):
		if "Args" in win11:
			args = win11["Args"]
		elif "args" in win11:
			args = win11["args"]
		else:
			return None
	else:
		args = win11
	if isinstance(args, list):
		if not args:
			return []
		cleaned = [arg for arg in args if isinstance(arg, str)]
		if len(cleaned) != len(args):
			logger.warning("Win11Debloat args contain non-string entries; ignoring invalid entries.")
		if cleaned:
			return cleaned
		return None
	if isinstance(args, str):
		return [args]
	logger.warning("Win11Debloat args are not a list or string; ignoring.")
	return None



def main(config_path=None):
	if getattr(sys, 'frozen', False):
		base_path = os.path.dirname(sys.executable)
	else:
		components_dir = os.path.dirname(os.path.abspath(__file__))
		base_path = os.path.dirname(components_dir)
	if config_path and isinstance(config_path, str) and _is_url(config_path):
		try:
			config_path = _download_config(config_path)
		except Exception as e:
			logger.error(f"Failed to download config: {e}")
			try:
				show_error_popup(
					f"Failed to download config from URL.\n{e}",
					allow_continue=False,
				)
			except Exception:
				pass
			sys.exit(1)
	default_config_path = os.path.join(base_path, 'configs', 'default.json')
	if not os.path.exists(default_config_path):
		logger.error(f"Default config not found: {default_config_path}")
		try:
			show_error_popup(
				f"Default config not found:\n{default_config_path}",
				allow_continue=False,
			)
		except Exception:
			pass
		sys.exit(1)
	default_config = _load_json_config(default_config_path, "default")

	user_config = None
	if config_path:
		if not os.path.exists(config_path):
			logger.error(f"Config not found: {config_path}")
			try:
				show_error_popup(
					f"Config not found:\n{config_path}",
					allow_continue=False,
				)
			except Exception:
				pass
			sys.exit(1)
		user_config = _load_json_config(config_path, "custom")
		logger.info(f"Using custom config: {config_path}")
	else:
		logger.info(f"Using default config: {default_config_path}")

	winutil_config = None
	win11debloat_args = None
	if user_config is not None:
		winutil_config = _extract_winutil_config(user_config)
		if winutil_config is None:
			logger.info("Custom config has no WinUtil section; using default WinUtil config.")
		win11debloat_args = _extract_win11debloat_args(user_config)
		if win11debloat_args is None:
			logger.info("Custom config has no Win11Debloat args; using default Win11Debloat args.")

	if winutil_config is None:
		winutil_config = _extract_winutil_config(default_config)
		if winutil_config is None:
			logger.error(f"Default config missing WinUtil section: {default_config_path}")
			try:
				show_error_popup(
					f"Default config missing WinUtil section:\n{default_config_path}",
					allow_continue=False,
				)
			except Exception:
				pass
			sys.exit(1)
	if win11debloat_args is None:
		win11debloat_args = _extract_win11debloat_args(default_config)
		if win11debloat_args is None:
			logger.warning("Default config has no Win11Debloat args; running without Win11Debloat flags.")
			win11debloat_args = []

	winutil_config_path = _write_temp_config(winutil_config, "talon_winutil_")
	logger.info(f"Using WinUtil config: {winutil_config_path}")
	winutil_path = os.path.join(base_path, 'external_scripts', 'winutil.ps1')
	if not os.path.exists(winutil_path):
		logger.error(f"Bundled WinUtil script not found: {winutil_path}")
		try:
			show_error_popup(
				f"Bundled WinUtil script not found:\n{winutil_path}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)
	cmd1 = f"& '{winutil_path}' -Config '{winutil_config_path}' -Run -NoUI"
	logger.info("Executing ChrisTitusTech WinUtil")
	try:
		run_powershell_command(
			cmd1,
			monitor_output=True,
			termination_str='Tweaks are Finished',
		)
		logger.info("Successfully executed ChrisTitusTech WinUtil")
	except Exception as e:
		logger.error(f"Failed to execute ChrisTitusTech WinUtil: {e}")
		try:
			show_error_popup(
				f"Failed to execute ChrisTitusTech WinUtil:\n{e}",
				allow_continue=False,
			)
		except Exception:
			pass
		sys.exit(1)
	win11debloat_path = os.path.join(base_path, 'external_scripts', 'Raphire-Win11Debloat-c523386', 'Win11Debloat.ps1')
	if not os.path.exists(win11debloat_path):
		logger.error(f"Bundled Win11Debloat script not found: {win11debloat_path}")
		try:
			show_error_popup(
				f"Bundled Win11Debloat script not found:\n{win11debloat_path}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)
	cmd2 = f"& '{win11debloat_path}'"
	if win11debloat_args:
		flags = ' '.join(win11debloat_args)
		cmd2 = f"& '{win11debloat_path}' {flags}"
	logger.info("Executing Raphi Win11Debloat")
	try:
		run_powershell_command(cmd2)
		logger.info("Successfully executed Raphi Win11Debloat")
	except Exception as e:
		logger.error(f"Failed to execute Raphi Win11Debloat: {e}")
		try:
			show_error_popup(
				f"Failed to execute Raphi Win11Debloat:\n{e}",
				allow_continue=False
			)
		except Exception:
			pass
		sys.exit(1)

	logger.info("All external debloat scripts executed successfully.")



if __name__ == "__main__":
	main()
