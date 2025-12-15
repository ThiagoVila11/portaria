def diamonds(r, c, s):
    result = []

    # 🔼 BLOCO SUPERIOR (todo o bloco superior repetido r vezes)
    for _ in range(r):
        for i in range(s):
            linecima = []
            linebaixo = []
            for _ in range(c):
                linecima.append("." * (s - i) + "/" + "." * (2 * i) + "\\" + "." * (s - i))
                linebaixo.append("." * (i + 1) + "\\" + "." * (2 * (s - i - 1)) + "/" + "." * (i + 1))
  
            result.append("".join(linecima))
            result.append("".join(linebaixo)) 
    return "\n".join(result)


print(diamonds(3,2, 2))