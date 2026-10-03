import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import 'reader_identity.dart';

/// Recorded model text remains the heading; a verified mark supports it.
class ReaderHeading extends StatelessWidget {
  const ReaderHeading({
    super.key,
    required this.observation,
    required this.name,
  });

  final Json observation;
  final String name;

  @override
  Widget build(BuildContext context) {
    final brand = readerBrand(observation);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (brand != null) ...[
          Image.asset(
            brand.asset,
            width: brand.width,
            height: context.ui.space.s6,
            fit: BoxFit.contain,
            alignment: AlignmentDirectional.centerStart,
            excludeFromSemantics: true,
          ),
          SizedBox(height: context.ui.space.s1),
        ],
        Text(name, style: context.ui.type.label),
      ],
    );
  }
}
