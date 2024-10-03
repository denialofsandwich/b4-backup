#!/usr/bin/bash

action=$1
volume_file=$2
mount_point=$3

#current_loop_dev=$(losetup | grep $volume_file | cut -d' ' -f 1)
pushd $(dirname $0)

if [[ "$action" == "mount" ]]; then
    echo "CREATE"

    dd if=/dev/zero of=$volume_file bs=1M count=200

    #loop_dev=$(sudo losetup -f)
    #echo $loop_dev
    #sudo losetup $loop_dev $volume_file

    #sudo mkfs.btrfs $loop_dev volume_file
    sudo mkfs.btrfs $volume_file

    sudo mkdir -p $mount_point
    #sudo mount $loop_dev $mount_point
    sudo mount $volume_file $mount_point
else
    echo "UNMOUNT"
    sudo umount $mount_point
    #sudo losetup -d $current_loop_dev

    sudo rm $volume_file
fi
