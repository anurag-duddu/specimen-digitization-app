import 'package:file_selector/file_selector.dart';

/// Image filters shared by file import, replacement, and recovery pickers.
/// iOS requires a uniform type identifier even when extensions are supplied.
const intakePhotoTypes = XTypeGroup(
  label: 'Photos',
  extensions: ['jpg', 'jpeg', 'png', 'tif', 'tiff', 'heic', 'heif', 'dng'],
  uniformTypeIdentifiers: ['public.image'],
);
