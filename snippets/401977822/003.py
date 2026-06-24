import psana
ds = psana.DataSource(exp='tmoc00123',run=19)
myrun = next(ds.runs())
det = myrun.Detector('mrco_hsd')
for nevt,evt in enumerate(myrun.events()):
   fex = det.raw.peaks(evt)
   fex_status = det.raw.fex_status(evt)
   print('****** event')
   for ndigi,(segment,fexdata) in enumerate(fex.items()):
       for nfex,(channel,fexchan) in enumerate(fexdata.items()):
           # channel is an idea where I believe in principle an                
           # hsd can put out several lower-frequency waveforms, but            
           # we only ever have channel 0.                                      
           # cpo doesn't currently understand the [1][0] indices here          
           print('segment',segment,'bkgd:',fex_status[segment][channel][1][0])
           startpos,peaks = fexchan
           for npeak,(start,peak) in enumerate(zip(startpos,peaks)):
               print('peak: start',start,'len',len(peak))
   if nevt>0: break