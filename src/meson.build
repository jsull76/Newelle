pkgdatadir = join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())
moduledir = join_paths(pkgdatadir, 'newelle')
gnome = import('gnome')

gnome.compile_resources('newelle',
  'newelle.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

# Explicitly specify Python version and dependencies
python_version : '3'
python = import('python')
python_exe = python.find_installation(python_version).get_executable()
if not python_exe:
    error('Python 3 not found!')

#Check for required dependencies
required_deps = ['gobject-introspection', 'gtk4', 'adw', 'gtksourceview5', 'pango', 'beautifulsoup4', 'requests']
for dep in required_deps:
    dep_check = dependency(dep)
    if not dep_check.found():
        error(f'Dependency "{dep}" not found!')

# Add build options
add_project_arguments(['-Werror'], language : 'c')
add_project_arguments(['-Werror'], language : 'cpp')
add_project_arguments(['-Werror'], language : 'vala')
add_project_arguments(['-Werror'], language : 'rust')
add_project_arguments(['-Werror'], language : 'fortran')
add_project_arguments(['-Werror'], language : 'd')
add_project_arguments(['-Werror'], language : 'swift')
add_project_arguments(['-Werror'], language : 'objectivec')
add_project_arguments(['-Werror'], language : 'objectivecpp')
add_project_arguments(['-Werror'], language : 'java')
add_project_arguments(['-Werror'], language : 'cs')
add_project_arguments(['-Werror'], language : 'go')
add_project_arguments(['-Werror'], language : 'nim')
add_project_arguments(['-Werror'], language : 'ada')
add_project_arguments(['-Werror'], language : 'fortran')
add_project_arguments(['-Werror'], language : 'f90')
add_project_arguments(['-Werror'], language : 'f95')
add_project_arguments(['-Werror'], language : 'f03')
add_project_arguments(['-Werror'], language : 'f08')
add_project_arguments(['-Werror'], language : 'f18')
add_project_arguments(['-Werror'], language : 'c++')
add_project_arguments(['-Werror'], language : 'c')
add_project_arguments(['-Werror'], language : 'vala')
add_project_arguments(['-Werror'], language : 'rust')
add_project_arguments(['-Werror'], language : 'fortran')
add_project_arguments(['-Werror'], language : 'd')
add_project_arguments(['-Werror'], language : 'swift')
add_project_arguments(['-Werror'], language : 'objectivec')
add_project_arguments(['-Werror'], language : 'objectivecpp')
add_project_arguments(['-Werror'], language : 'java')
add_project_arguments(['-Werror'], language : 'cs')
add_project_arguments(['-Werror'], language : 'go')
add_project_arguments(['-Werror'], language : 'nim')
add_project_arguments(['-Werror'], language : 'ada')
add_project_arguments(['-Werror'], language : 'fortran')
add_project_arguments(['-Werror'], language : 'f90')
add_project_arguments(['-Werror'], language : 'f95')
add_project_arguments(['-Werror'], language : 'f03')
add_project_arguments(['-Werror'], language : 'f08')
add_project_arguments(['-Werror'], language : 'f18')


conf = configuration_data()
conf.set('PYTHON', python_exe)
conf.set('VERSION', meson.project_version())
conf.set('localedir', join_paths(get_option('prefix'), get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'newelle.in',
  output: 'newelle',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'r-xr--r--'
)

newelle_sources = [
  '__init__.py',
  'main.py',
  'gtkobj.py',
  'constants.py',
  'settings.py',
  'window.py',
  'shortcuts.py',
  'thread_editing.py',
  'extension.py',
  'llm.py',
  'tts.py',
  'stt.py',
  'extra.py',
  'presentation.py',
  'handler.py'
]

install_data(newelle_sources, install_dir: moduledir)
