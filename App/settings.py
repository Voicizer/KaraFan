#!python3.10

#   MIT License - Copyright (c) 2023 Captain FLAM
#
#   https://github.com/Captain-FLAM/KaraFan

import os, configparser

# Default values
defaults = {
	'PATHS': {
		'input': "Music",
		'output': "Results",
	},
	'PROCESS': {
		'output_format': "FLAC",
#		'preset_genre': "Pop Rock",
		'instru_1': "Instrum HQ 3",
		'vocals_1': "Kim Vocal 2",
		'vocals_2': "Voc FT",
		'filter_1': "Instrum HQ 3",
		'filter_2': "Instrum Main",
		'filter_3': "Vocal Main",
		'filter_4': "Model 9662"
	},
	'OPTIONS': {
		'normalize': False,
		'large_gpu': True,
		'shifts_vocals': 12,
		'shifts_instru': 12,
		'shifts_filter': 3,
#		'overlap_MDXv3': 8,
		'chunk_size': 500000,
	},
	'BONUS': {
		'TEST_MODE': False,
		'DEBUG': False,
		'GOD_MODE': False,
		'PREVIEWS': False,
	},
}

def Convert_to_Options(config):

	options = {}
	options['input']			= config['PATHS']['input']
	options['output']			= config['PATHS']['output']
	options['output_format']	= config['PROCESS']['output_format']
#	options['preset_genre']		= config['PROCESS']['preset_genre']
	options['instru_1']			= config['PROCESS']['instru_1']
	options['vocals_1']			= config['PROCESS']['vocals_1']
	options['vocals_2']			= config['PROCESS']['vocals_2']
	options['filter_1']			= config['PROCESS']['filter_1']
	options['filter_2']			= config['PROCESS']['filter_2']
	options['filter_3']			= config['PROCESS']['filter_3']
	options['filter_4']			= config['PROCESS']['filter_4']
	options['normalize']		= (config['OPTIONS']['normalize'].lower() == "true")
	options['large_gpu']		= (config['OPTIONS']['large_gpu'].lower() == "true")
	options['shifts_vocals']	= int(config['OPTIONS']['shifts_vocals'])
	options['shifts_instru']	= int(config['OPTIONS']['shifts_instru'])
	options['shifts_filter']	= int(config['OPTIONS']['shifts_filter'])
#	options['overlap_MDXv3']	= int(config['OPTIONS']['overlap_MDXv3'])
	options['chunk_size']		= int(config['OPTIONS']['chunk_size'])
	options['TEST_MODE']		= (config['BONUS']['TEST_MODE'].lower() == "true")
	options['DEBUG']			= (config['BONUS']['DEBUG'].lower() == "true")
	options['GOD_MODE']			= (config['BONUS']['GOD_MODE'].lower() == "true")
	options['PREVIEWS']			= (config['BONUS']['PREVIEWS'].lower() == "true")

	return options

def Load(Gdrive, isColab):

	global defaults
	file = os.path.join(Gdrive, "KaraFan_user", "Config_Colab.ini" if isColab else "Config_PC.ini")
	
	config = configparser.ConfigParser()
	config.optionxform = lambda option: option  # To preserve case of Keys !!

	if os.path.isfile(file):
		config.read(file, encoding='utf-8')
		
		# Load default values if not present
		for section in defaults:
			if section not in config:
				config[section] = {}
			for key in defaults[section]:
				if key not in config[section]:
					config[section][key] = str(defaults[section][key])
	else:
		config.read_dict(defaults)
		Save(Gdrive, isColab, config)
	
	return config

def Save(Gdrive, isColab, config):
	
	file = os.path.join(Gdrive, "KaraFan_user", "Config_Colab.ini" if isColab else "Config_PC.ini")

	with open(file, 'w') as config_file:
		config.write(config_file)
	