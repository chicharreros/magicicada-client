Magicicada Client
=================

![tests](https://github.com/chicharreros/magicicada-client/actions/workflows/tests.yml/badge.svg)

This project is a fork of the Ubuntu One client project.


Details
-------

In order to run tests in ubuntuone-client, you can simply bootstrap and
everything will be setup automagically:

$: sudo apt-get install make
$: make bootstrap

After configuring, in order to run the tests, all you need to do is run
make test.

$: make test


Magicicada uses branch based development on Github, and bugs to track
features and issues. Make sure a bug is filed for the piece of code you wish
to work on. When committing your changes, be sure to specify the bug # it
fixes.

After pushing your branch, you will need to propose it for merging into the
main branch. In order for your branch to be accepted, it needs to ensure all
existing tests keep passing, and the code you are adding/modifying has the
proper addings/modifications in the tests/ folder. Your branch will also need
at least one Magicicada developers (the chicharreros team) positive vote before
landing.
