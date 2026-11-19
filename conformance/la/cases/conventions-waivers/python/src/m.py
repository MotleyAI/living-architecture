X = 1
import a  # ALLOW(import-not-top): circular import with b
import b  #ALLOW(import-not-top):x
import c  # ALLOW(composite-assert): wrong rule
import d  # ALLOW(import-not-top):
import e  # allow(import-not-top): lowercase
