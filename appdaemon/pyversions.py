import sys

"""
Function to switch code for different python versions and functions to implement them

Functions should be created in pairs, one for the lower version, one for the higher.
The tuple supplied as the version parameters represents the FIRST version that is
required to run the higher version variant. If the environment being run in is equal to or greater than
this version number, the "ge" (greater or equal) variant will be run, other wise the "lt" (less than) variant will
be run.

There is a convention here to avoid confusion - name both variants as follows:

    <base name for the function>_<variant>_<version>

    <variant> is either "lt" or "ge"
    <version> is the python version used as the cutoff as a concatenated string with no periods

    e.g.

    def test_lt_376()
        ...

    def test_ge_376()
        ...



"""

# Switcher


def pyvercheck(version, lt, ge, *args, **kwargs):
    """

    :param version: A 3 entry list describing the cutoff version, e.g. (3, 7, 6)
    :param lt: function to be called if version is less than the cutoff
    :param ge: function to be called if version is greater than or equal to the cutoff
    :param args: optional list of fixed args
    :param kwargs: optional list of keyword args
    :return: whatever the function returns

    Example:

    import appdaemon.pyversions as pyversions
    value = pyversions.pyvercheck((3, 7, 6), pyversions.test_lt_376, pyversions.test_ge_376, 1, 2, 3, fruitbat=24)

    """
    if sys.version_info < version:
        return lt(*args, **kwargs)
    else:
        return ge(*args, **kwargs)


# Example function pair


def test_lt_376(a, b, c, **kwargs):
    print("I should only be called for less than 3.7.6")
    print(a, b, c)
    print(kwargs["fruitbat"])
    return 4


def test_ge_376(a, b, c, **kwargs):
    print("I should only be called for greater than or equal to 3.7.6")
    print(a, b, c)
    print(kwargs["fruitbat"])
    return 4
