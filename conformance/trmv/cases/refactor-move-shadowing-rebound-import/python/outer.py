def outer():
    import pkg.a as pa

    def reset():
        nonlocal pa
        import pkg.a as pa

    reset()
    return pa.f()
