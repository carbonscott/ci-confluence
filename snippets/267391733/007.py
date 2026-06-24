import h5py
f = h5py.File("mysmallh5.h5", "r")
n1 = f['timestamp']
n2 = f['var_test_len']
n3 = f['var_test/x']
n4 = f['var_test/y']
print(len(n1), len(n2))
idx = 0
for i in range(len(n1)):
    print("%d --> %d" % (n1[i], n2[i]))
    for j in range(n2[i]):
        print( "    %s | %s" % (n3[idx+j], n4[idx+j]))
    print("")
    idx += n2[i]