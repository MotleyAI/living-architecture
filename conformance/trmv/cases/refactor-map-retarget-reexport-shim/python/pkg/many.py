from pkg.compat_aug import AcmeModel as Aug
from pkg.compat_append import AcmeModel as App
from pkg.compat_extend import AcmeModel as Ext
from pkg.compat_annotated import AcmeModel as Ann
from pkg.compat_pep484 import AcmeModel as Pep

made = Aug(), App(), Ext(), Ann(), Pep()
