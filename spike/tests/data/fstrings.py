name = "w"
width = 10
prec = 3
value = 1.5
xs = ["a", "b"]

a = f"hello {name}!"
b = F"{{literal}} {name!r:>{width}} }}"
c = f"{value:{width}.{prec}f}"
d = "plain " f"{name}" 'tail'
e = rb"raw\d" + Rb'x' + BR"y"
g = fR"{name}\d" + Rf'{width}' + u"unicode"
h = f"""multi
{name}
line {value:>{width}}"""
n = f"{f'{name}'}"
s = f'{"inner"}' f"{name=}" f"{name = !s:>4}"
q = f"{xs[0]}{width + prec}" "" f""
