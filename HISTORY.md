=======
History
=======

1.1.0 (2016-21-09)
------------------

* Features

- Installation via pip3 - contributed by [Martin Hjelmare[(https://github.com/MartinHjelmare) 
- Allow use of STDERR and SDTOUT as logfile paths to redirect to stdout and stderr respectively - contributed by [Jason Hite](https://github.com/jasonmhite)
- Deprecated "timezone" directive on cfg file in favor of "time_zone" for consistency with Home Assistant config

* Fixes

- Fix to give more information if initial connect to HA fails (but still avoid spamming logs too badly if it restarts)
- Rename 'init' directory to 'scripts'
- Tidy up docs

* Breaking Changes

- As a result of the repackaging for PIP3 installation, all apps must be edited to change the import statement of the api to `import appdaemon.appapi as appapi`
- timezone is deprecated but still works

1.0.0 (2016-08-09)
------------------

* Initial Release
