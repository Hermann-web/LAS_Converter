#!/usr/bin/env python
'''
    LAS_CSV_Converter.py : This python script is intended to convert LIDAR LAS files to and from CSV format
                            the script can also modify the existing points using a webservice call or an implemented function
'''

__author__ = "Hieu Nguyen"
__copyright__ = "Copyright 2017, Hieu Nguyen"
__version__ = "1.0"
__status__ = "Development"

import numpy as np
import datetime
import time
import requests
import sys
import shutil
import csv
from laspy import *
import xml.etree.ElementTree as elt

# LASFileManager : handles IO streams of LAS to CSV
class LASFileManager:

    def __init__(self, infilename, outfilename):
        self.inFileName = infilename
        self.outFileName = outfilename

        self.readStream = None
        self.writeStream = None

        self.fileInfo = None

    def open_read_stream(self):
        self.readStream = file.File(self.inFileName, mode='rw')

        num_points = self.readStream.__len__()

        # Obtain offsets and scaling values
        x_offset = self.readStream.header.offset[0]
        y_offset = self.readStream.header.offset[1]
        z_offset = self.readStream.header.offset[2]

        x_scale = self.readStream.header.scale[0]
        y_scale = self.readStream.header.scale[1]
        z_scale = self.readStream.header.scale[2]

        header_size = sum(1 for i in self.readStream.point_format)
        attributes = []

        # Obtain the header information
        for attribute in self.readStream.point_format:
            attributes.append(attribute.name)

        # init file information
        self.fileInfo = FileInfo(num_points,
                                 x_offset, y_offset, z_offset,
                                 x_scale, y_scale, z_scale,
                                 header_size, attributes)

    def close_read_stream(self):
        self.readStream.close()

    def open_write_stream(self):
        self.writeStream = open(self.outFileName, mode='w')

    def close_write_stream(self):
        self.writeStream.close()

    def writeln(self, content):
        self.writeStream.write(content + "\n")


# CSVFileManager : handles IO streams of CSV to LAS
class CSVFileManager:

    def __init__(self, infilename, outfilename):
        self.infilename = infilename
        self.outfilename = outfilename

        self.readStream = None
        self.writeStream = None

        self.X_points = []
        self.Y_points = []
        self.Z_points = []


    def open_read_stream(self):
        # self.readStream = open(self.infilename, mode='r')
        self.readStream = csv.reader(open(self.infilename, mode='r'), delimiter=' ')

    def close_read_stream(self):
        self.readStream.close()

    def open_write_stream(self, head):
        self.writeStream = file.File(self.outfilename, mode='w', header=head)

    def close_write_stream(self):
        self.writeStream.close()

    def add_point(self, x, y, z):
        self.X_points.append(x)
        self.Y_points.append(y)
        self.Z_points.append(z)

    def load_points(self):
        for row in self.readStream:
            self.add_point(row[0], row[1], row[2])

    def push_points(self):
        self.writeStream.X = np.array(self.X_points)
        self.writeStream.Y = np.array(self.Y_points)
        self.writeStream.Z = np.array(self.Z_points)

    def set_header_info(self, _file_signature, _date, _min, _max, _version, _offset, _scale, _software_id, _system_id):
        #self.writeStream.header.file_signature = _file_signature
        self.writeStream.header.date = datetime.datetime(_date[0], _date[1], _date[2])
        #self.writeStream.header.file_source_id
        #self.writeStream.header.guid

        self.writeStream.header.max = _max
        self.writeStream.header.min = _min

        _major, _minor = _version.split(".")
        self.writeStream.header.major_version = _major
        self.writeStream.header.minor_version = _minor

        self.writeStream.header.offset = _offset
        self.writeStream.header.scale = _scale

        self.writeStream.header.software_id = '{:<32}'.format(_software_id[:32])
        self.writeStream.header.system_id = '{:<32}'.format(_system_id[:32])


# FileInfo : holds onto information of the file
class FileInfo:

    def __init__(self, num_points, x_offset, y_offset, z_offset,
                                 x_scale, y_scale, z_scale,
                                 header_size, attributes):

        self.num_points = num_points
        self.x_offset = x_offset
        self.y_offset = y_offset
        self.z_offset = z_offset
        self.x_scale = x_scale
        self.y_scale = y_scale
        self.z_scale = z_scale
        self.header_size = header_size
        self.attributes = attributes

    def get_header(self):
        head = ""
        index = 0

        for att in self.attributes:
            index += 1
            head += str(att)

            if index < self.header_size:
                head += ","

        return head

class WebService:

    def __init__(self, service_url, model, frame, epoch, tocsv):
        self.service_url = service_url
        self.model = model
        self.frame = frame
        self.epoch = epoch
        self.tocsv = tocsv

        self.lang = "en"
        self.conversion = "on"
        self.projection = "geo"
        self.westpos = "true"

    def setConversionType(self, type, projection):
        if type == "batch":
            self.service_url = 'https://webapp.geod.nrcan.gc.ca/CSRS/tools/GPSH/upload'
        elif type == "CGG2013a":
            self.service_url = 'https://webapp.geod.nrcan.gc.ca/CSRS/tools/GPSH/CGG2013a'
        elif type == "HT2_0_CGG2013a":
            self.service_url = 'https://webapp.geod.nrcan.gc.ca/CSRS/tools/GPSH/HT2_0_CGG2013a'

        self.projection = projection

        return self.service_url

    # call to GPSH webservice
    def batch_call(self, in_file):
        self.setConversionType("batch", self.conversion)

        post_fields = {
            # "lang":lang,
            # "conversion":"on",
            "model": self.model,
            "frame": self.frame,
            "epoch": self.epoch
        }

        files = {'file': open(in_file)}

        # TODO : web service cannot handle large files, crashes with >600 000 lines
        # post request
        req = requests.post(self.service_url, data=post_fields, files=files)

        # print intermediate csv
        if self.tocsv:
            with open('output.csv', mode='w') as _file:
                _file.write(req.text)

        # parse http response
        data = req.text.split("\n")
        header = data.pop(0)
        matrix = np.array([header.split(",")])
        siz = len(data)
        count = 0

        for row in data:
            row_data = np.array([row.split(",")])
            if len(matrix[0]) == len(row_data[0]):
                matrix = np.append(matrix, row_data, axis=0)

            count += 1
            #if count % 1000 == 0:
            #    print(str(count) + " / " + str(siz))

        return matrix

    def single_point(self, x, y, z, type=None, projection=None, lang=None, conversion=None, westpos=None, model=None, frame=None, epoch=None):

        if type != None: self.setServiceURL(type)
        self.projection = projection if projection != None else self.projection
        self.lang = lang if lang != None else self.lang
        self.conversion = conversion if conversion != None else self.conversion
        self.westpos = westpos if westpos != None else self.westpos
        self.model = model if model != None else self.model
        self.frame = frame if frame != None else self.frame
        self.epoch = epoch if epoch != None else self.epoch

        # dict of params to send to the web service
        data = {
            'lang': self.lang,
            'proj': self.projection,
            'conversion': self.conversion,
            'westpos': self.westpos,
            #'conversionModel': '',
            #'geoidModel': '',
            'model': self.model,
            'frame': self.frame,
            'epoch': self.epoch,
            'x': x,
            'y': y,
            'z': z,
            'westpos': self.westpos
        }

        if self.projection == "plan": data["zone"] = "ON-9"

        req = requests.get(self.service_url, data)
        #print(req.text)

        # TODO : return the parsed xml as iterable data structure
        return req.text


# INCOMPLETE - this function has not yet been fully implemented
def csv_to_las(input_file_name, output_file_name):

    manager = CSVFileManager(input_file_name, output_file_name)

    head = header.Header()

    #manager.open_read_stream()
    manager.open_write_stream(head)

    #inFile = manager.readStream
    outFile = manager.writeStream

    file_sig = 'LASF'
    date = [2013,6,4]
    maxx = [330786.99,4840757.20,990.56]
    minn = [329127.03, 4839565.68, 4839565.68]
    offset = [329999.8947, 4839000.0062, 0.0]
    scale = [0.0001, 0.0001, 0.0001]
    soft_id = "software_id"
    sys_id = "system_id"
    version = "1.2"

    manager.set_header_info(file_sig,date,minn,maxx,version,offset,scale,soft_id,sys_id)

    manager.add_point(329999.8947,4839000.0062,0.671)
    manager.add_point(330002.2338,4838999.6872,0.617)
    manager.add_point(330026.3268,4839042.692,0.417)
    manager.add_point(330047.6052,4839040.4722,0.7269)
    manager.add_point(330051.1468,4839040.851,0.645)
    manager.add_point(330020.8758,4839046.2249,0.2888)

    manager.push_points()

    #manager.close_read_stream()
    manager.close_write_stream()

# las_to_csv : pretty self explanatory
def las_to_csv(input_file_name, output_file_name):

    fileManager = LASFileManager(input_file_name, output_file_name)

    # open read and write streams
    fileManager.open_read_stream()
    fileManager.open_write_stream()

    # get streams
    inFile = fileManager.readStream
    outFile = fileManager.writeStream

    # get file information
    file_info = fileManager.fileInfo

    # write header information to csv
    outFile.write(file_info.get_header() + "\n")

    attributes = file_info.attributes

    # counter for progress
    progressCounter = 0
    progressMax = file_info.num_points

    # write point information to csv
    for points_list in inFile.points:

        for points in points_list:

            lineValues = []
            line = ""
            index = 0

            for attribute in points:

                # obtain actual value after accounting for scaling and offset values
                if attributes[index] == "X":
                    outValue = ( attribute * file_info.x_scale ) + file_info.x_offset
                elif attributes[index] == "Y":
                    outValue = ( attribute * file_info.y_scale ) + file_info.y_offset
                elif attributes[index] == "Z":
                    outValue = ( attribute * file_info.z_scale ) + file_info.z_offset
                else:
                    outValue = attribute

                lineValues.append(outValue)
                line += (str(outValue))

                if index < file_info.header_size-1:
                    line += ","

                index += 1

            outFile.write(line + "\n")

        progressCounter += 1

        if progressCounter % 1000 == 0:
            print(str(progressCounter) + " / " + str(progressMax))
            # break

    # close streams
    inFile.close()
    outFile.close()

# las_to_csv_sub : extracts only x,y,z values to be transformed
def las_to_csv_sub(input_file_name, output_file_name, utm_zone):

    fileManager = LASFileManager(input_file_name, output_file_name)

    # open read and write streams
    fileManager.open_read_stream()
    fileManager.open_write_stream()

    # get streams
    inFile = fileManager.readStream
    outFile = fileManager.writeStream

    # get file information
    file_info = fileManager.fileInfo

    # write header information to csv
    outFile.write("utm_e,utm_n,height,utm_z" + "\n")

    attributes = file_info.attributes

    # counter for progress
    progressCounter = 0
    progressMax = file_info.num_points

    # write point information to csv
    for points_list in inFile.points:

        for points in points_list:

            lineValues = []
            line = ""
            index = 0

            for attribute in points:

                # obtain actual value after accounting for scaling and offset values
                if attributes[index] == "X":
                    outValue = ( attribute * file_info.x_scale ) + file_info.x_offset
                elif attributes[index] == "Y":
                    outValue = ( attribute * file_info.y_scale ) + file_info.y_offset
                elif attributes[index] == "Z":
                    outValue = ( attribute * file_info.z_scale ) + file_info.z_offset
                elif index == 3:
                    outValue = utm_zone
                else:
                    break
                    outValue = attribute

                lineValues.append(outValue)
                line += (str(outValue))

                if index < 3:
                    line += ","

                index += 1

            outFile.write(line + "\n")

        progressCounter += 1

        if progressCounter % 1000 == 0:
            print(str(progressCounter) + " / " + str(progressMax))

        # limit number of file to calculate
        #if progressCounter >= 500000:
        #    break

    # close streams
    inFile.close()
    outFile.close()

# returns a list of of elements defined by the height code header
def extract_height(matrix, height_code):
    header = matrix[:1][0]
    res = []

    for i in range(len(header)):
        if header[i] == height_code:
            res.append(i)

    return matrix[1:, res[0]]

def parse_request_XML(xml):
    return None

# Main Script

# debugging file names
in_file = "90000.las"
pre_web_service = "prewb.temp.csv"

pre_mod = "converted_"
out_file = pre_mod + in_file

# open streams
file_manager = LASFileManager(in_file, "")
file_manager.open_read_stream()
readStream = file_manager.readStream
main_file = file_manager.fileInfo

starttime = time.time()

# Batch conversion ----------------------------------------------------------------------------------------
# TODO : partition LAS points into separate csv files to be sent to the webservice
wbservice = WebService("", "HT2_0_CGG2013a", "NAD83%28CSRS%29", "1997-01-01", False)
wbservice.setConversionType("HT2_0_CGG2013a","plan")

las_to_csv_sub(in_file,pre_web_service,"ON-9")
matrix = wbservice.batch_call(pre_web_service)

# create a copy of the file to be modified
shutil.copy(in_file, out_file)

file_manager2 = LASFileManager(out_file, "")
file_manager2.open_read_stream()
rwStream = file_manager2.readStream
batch_file = file_manager2.fileInfo

# Note: Will throw exception because points are being limited above
new_heights = extract_height(matrix,"H2013").astype(np.float)
for i in range(len(new_heights)):
    new_heights[i] = (new_heights[i] - batch_file.z_offset) / batch_file.z_scale

print(rwStream.Z)
print(new_heights)
rwStream.Z = new_heights
rwStream.close()

# End batch conversion -----------------------------------------------------------------------------------


# Single Point Conversion Loop ---------------------------------------------------------------------------
#writeStream = open("compare.csv", mode='w')
#
#print("Webservice call")
#
## Instantiate webservice class
#wbservice = WebService("", "HT2_0_CGG2013a", "NAD83%28CSRS%29", "1997-01-01", False)
#wbservice.setConversionType("HT2_0_CGG2013a","plan")
#
## iterate over points in the las file
#for i in range(readStream.__len__()):
#    # calculate actual point and send to the webservice
#    res = wbservice.single_point(readStream.X[i] * main_file.x_scale + main_file.x_offset,readStream.Y[i] * main_file.y_scale + main_file.y_offset,readStream.Z[i] * main_file.z_scale + main_file.z_offset)
#
#    # extract information from xml dom
#    root = elt.fromstring(res)
#
#    # height for debugging
#    z =  (readStream.Z[i] - main_file.z_offset) / main_file.z_scale
#    writeStream.write(str(z) + "," + root[8].text + "\n")
#
#    # write new height to the las file
#    readStream.Z[i] = (float(root[8].text) - main_file.z_offset) / main_file.z_scale
#
#    # progress counter for debugging
#    #if i % 100 == 0 :
#    print(str(i) + " / " + str(readStream.__len__()))
#        #break
#
## close io streams
#writeStream.close()

# End single point conversion --------------------------------------------------------------------------

readStream.close()

# elapsed time in seconds
endtime = time.time()
difftime = endtime - starttime
print("Time:" + str(starttime) + " - " + str(endtime) + " = " + str(difftime))

print("Script Terminating")